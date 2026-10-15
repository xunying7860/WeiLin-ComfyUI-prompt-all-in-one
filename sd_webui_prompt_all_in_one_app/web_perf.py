"""
web_perf.py —— WeiLin 插件 web 传输优化层（落地 03_web_perf.py，方案 §B5 / §B6 / §B9 / P2-1）
================================================================================

解决的问题：每次刷新 / 打开节点都要把大文件重新明文传一遍。

覆盖点与收益：
  - /sd-webui-prompt-all-in-one-js  736KB 明文、每次 os.listdir+读盘拼接(实测 25.8ms)
        -> 打包结果按目录 mtime 缓存，命中后 0 次读盘；带 ETag，二次刷新 304 零传输；支持 gzip
  - /weilin/web_ui/* 静态资源（裸 FileResponse，无任何缓存头）
        -> 加 Cache-Control（静态资源 max-age=86400，其余 /weilin/ 走 no-cache 以便 304）
  - 所有 web.Response（json/css/js/html 等）> 1KB 且客户端接受 gzip 时自动压缩

实现方式：ComfyUI 的 aiohttp Application 已经创建完毕、插不了 middleware，
但 aiohttp 允许运行时给 app.on_response_prepare 信号追加回调 —— 效果等价。

相对补丁原码修正的三处（原码在真实 aiohttp 3.14 上会踩坑）：
  1) StreamResponse(FileResponse / WebSocketResponse) 没有 .body 属性，直接 `response.body`
     会抛 AttributeError 并让该路由 500（on_response_prepare 回调异常会打断 prepare）。
     统一改成 getattr(response, "body", None) 兜底判空。
  2) gzip 只压缩一次，Content-Length 与 body 复用同一份结果（原码 compress 了两次）。
  3) ETag 只对 GET 加（POST 响应加 ETag 无意义，且会污染写操作响应）。
"""

from __future__ import annotations

import gzip
import os
from hashlib import md5

from aiohttp import web

# 小于 1KB 不压，省 CPU（压缩本身也要花时间，小响应得不偿失）
_GZIP_MIN = 1024
# 只压缩这些「文本/可压缩」类型；已经在别处压缩过的、二进制的都不碰
_GZIP_TYPES = (
    "application/json", "javascript", "text/css", "text/html",
    "text/plain", "application/javascript", "text/xml", "svg",
)
# 内容基本不变的资源前缀：可以放心用较长的浏览器强缓存
_IMMUTABLE_PREFIXES = ("/weilin/web_ui/", "/weilin/lorainfo/api/loras/img")


def make_on_prepare():
    """
    构造 on_response_prepare 回调（gzip + ETag + 缓存头）。

    单独抽成工厂函数，一是方便 install_web_perf 安装，二是方便在脱离 ComfyUI 的
    mini aiohttp app 里做单元冒烟（直接 append 到 TestServer 的 app 上）。
    """

    async def on_prepare(request, response):
        # ---- 1) 缓存头 ----
        path = request.rel_url.path
        if path.startswith(_IMMUTABLE_PREFIXES):
            # 前端静态资源 / 封面图：内容基本不变，允许浏览器直接用旧副本
            response.headers.setdefault("Cache-Control", "public, max-age=86400")
        elif path.startswith("/weilin/"):
            # 其余 /weilin/ 接口：允许 304，但不允许不经校验就用旧副本
            response.headers.setdefault("Cache-Control", "no-cache")

        # StreamResponse(FileResponse/WebSocketResponse) 没有 .body 属性，用 getattr 兜底。
        # FileResponse 走 sendfile/流式输出，body 为 None —— 后面的 gzip 会据此跳过。
        body = getattr(response, "body", None)

        # ---- 2) ETag（仅 GET，且仅对确实持有内存 body 的响应）----
        if request.method == "GET" and body is not None and "ETag" not in response.headers:
            raw = body if isinstance(body, bytes) else str(body).encode("utf-8")
            response.headers["ETag"] = '"%s"' % md5(raw).hexdigest()

        # ---- 3) gzip ----
        if "gzip" not in request.headers.get("Accept-Encoding", "").lower():
            return
        # 非可压缩类型直接跳过（content_type 为空时按可压缩处理，交由类型白名单语义）
        if response.content_type and not any(t in response.content_type for t in _GZIP_TYPES):
            return
        # 已经压缩过的（例如 js_bundle_route 自己压好的）不要再压一遍
        if "Content-Encoding" in response.headers:
            return
        if body is None:                       # FileResponse 等流式响应跳过 gzip
            return
        raw = body if isinstance(body, bytes) else str(body).encode("utf-8")
        if len(raw) < _GZIP_MIN:               # 太小不压
            return
        # 只压缩一次：同一份 gz 既用于 Content-Length 也用于 body（原码压了两次）
        gz = gzip.compress(raw, 6)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Vary"] = "Accept-Encoding"
        response.headers["Content-Length"] = str(len(gz))
        response.body = gz

    return on_prepare


def install_web_perf():
    """
    把优化层挂到 ComfyUI 运行中的 aiohttp app 上（在 app_start() 最前面调用）。

    返回安装好的回调，方便做「是否重复安装」的判断；拿不到 app 时返回 None。
    """
    try:
        from server import PromptServer
        app = getattr(PromptServer, "instance", None)
        app = getattr(app, "app", None)
    except Exception as e:  # server 模块或实例尚未就绪时不要让插件启动整体崩掉
        print(f"[WeiLin][web_perf] 取 PromptServer.app 失败，跳过传输优化层：{e!r}")
        return None

    if app is None:
        print("[WeiLin][web_perf] PromptServer.app 尚未就绪，跳过传输优化层")
        return None

    handler = make_on_prepare()
    app.on_response_prepare.append(handler)
    return handler


# ---------------------------------------------------------------- JS bundle 打包缓存
# 目录内容未变时不重读盘；只按目录内 *.js 的最大 mtime 判断是否需要重建。
_BUNDLE = {"mtime": None, "etag": "", "js": b"", "gz": b""}


def _rebuild(js_dir: str):
    """重新读盘、拼接、压缩、算 ETag，写回模块级缓存。"""
    names = []
    newest = 0.0
    for name in sorted(os.listdir(js_dir)):
        if not name.endswith(".js"):
            continue
        st = os.stat(os.path.join(js_dir, name))
        names.append(name)
        newest = max(newest, st.st_mtime)

    # 拼接方式与原 app.py handler 完全一致：每个文件内容 + '\n'，保证返回文本逐字节不变
    chunks = []
    for name in names:
        with open(os.path.join(js_dir, name), "r", encoding="utf-8") as f:
            chunks.append(f.read())
    data = ("\n".join(chunks) + "\n").encode("utf-8")

    _BUNDLE.update({
        "mtime": newest,
        "js": data,
        "gz": gzip.compress(data, 6),
        "etag": '"%s"' % md5(data).hexdigest(),
    })
    return data


def js_bundle_route(js_dir: str):
    """
    替换 app.py 里 /sd-webui-prompt-all-in-one-js 的处理函数。

    相比原实现（每次 os.listdir + 读 736KB 并拼接）：
      - 仅在目录内 js 的最大 mtime 变化时才重读盘拼接，否则直接命中内存缓存；
      - 带 ETag：If-None-Match 命中直接 304 零传输；
      - 支持 gzip（预压缩缓存，压缩也只做一次）。
    返回的 js 文本与原实现逐字节相同（URL 路径仍由 app.py 注册为原路径）。
    """

    async def handler(request):
        js_dir_abs = os.path.abspath(js_dir)
        if not os.path.isdir(js_dir_abs):
            return web.Response(status=404, text="js dir not found")

        # 先廉价地取一次目录内最大 mtime，只有它变了才真正读盘
        newest = 0.0
        for name in os.listdir(js_dir_abs):
            if not name.endswith(".js"):
                continue
            newest = max(newest, os.stat(os.path.join(js_dir_abs, name)).st_mtime)

        if newest != _BUNDLE["mtime"] or not _BUNDLE["etag"]:
            _rebuild(js_dir_abs)

        etag = _BUNDLE["etag"]
        if request.headers.get("If-None-Match") == etag:
            # 命中：304，只回一个 ETag，body 为空
            return web.Response(status=304, headers={
                "ETag": etag, "Cache-Control": "no-cache",
            })
        if "gzip" in request.headers.get("Accept-Encoding", "").lower():
            return web.Response(
                status=200, body=_BUNDLE["gz"],
                content_type="application/javascript",
                headers={
                    "Content-Encoding": "gzip", "ETag": etag,
                    "Cache-Control": "no-cache", "Vary": "Accept-Encoding",
                },
            )
        return web.Response(
            status=200, body=_BUNDLE["js"],
            content_type="application/javascript",
            headers={"ETag": etag, "Cache-Control": "no-cache"},
        )

    return handler
