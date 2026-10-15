import sys
import os

AIO_PATH = os.path.join(os.path.dirname(__file__), "sd_webui_prompt_all_in_one")
sys.path.append(AIO_PATH)

# [P0-1] 移除 gradio 导入：ComfyUI 环境里它只用于一个类型注解，冷 import ~1-3s 每次启动都付（方案A3）
from server import PromptServer
from aiohttp import web
from .sd_webui_prompt_all_in_one.scripts.on_app_started import on_app_started
from .install import run_install
# [P2-1] 传输优化层：gzip + ETag + 缓存头 + js 打包缓存（方案 §B5/B6/P2-1）
from .web_perf import install_web_perf, js_bundle_route

def app_start():

    # [P2-1] 最先安装响应优化层：给运行中的 aiohttp app 追加 on_response_prepare 信号
    install_web_perf()

    # 安装依赖
    # [P0-2] 丢后台线程 + install.py 内 .installed 标记：启动不再等子进程（方案A1）
    import threading
    threading.Thread(target=run_install, name="weilin-install", daemon=True).start()

    static_path = os.path.join(os.path.dirname(__file__), "../prompt_static/")
    js_dir = os.path.join(os.path.dirname(__file__), "../prompt_js/")

    # [P2-1] 原实现：每次请求 os.listdir + 读盘拼接 736KB 明文（实测 25.8ms，无 ETag/gzip/Cache-Control）。
    # 改为带 ETag/304/gzip 且按目录 mtime 缓存打包结果的 handler；URL 路径保持完全不变。
    PromptServer.instance.routes.get("/sd-webui-prompt-all-in-one-js")(
        js_bundle_route(js_dir)
    )

    @PromptServer.instance.routes.get("/weilin/web_ui/{file_path:.*}")
    async def _getWebUI(request):
        file_path = request.match_info.get('file_path', '')
        full_path = os.path.join(static_path, file_path)
        # 检查文件路径是否存在
        if os.path.isfile(full_path):
            return web.FileResponse(full_path)
        raise web.HTTPNotFound()

    print("====== WeiLin prompt-all-in-one =====")
    print(f"APP is running  WeiLin prompt-all-in-one!.")
    print(f"WeiLinComfyUIPromptAllInOne 节点已启动成功!.")