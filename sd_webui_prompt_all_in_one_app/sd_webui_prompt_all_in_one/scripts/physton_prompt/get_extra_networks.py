# -*- coding: UTF-8 -*-
"""
get_extra_networks.py — Lora 面板数据接口（方案 B1/B2、P1-3 重写）
==================================================================
原实现三个事件循环问题（本次已修复）：
  1. ThreadPoolExecutor 里对每个 lora 调 asyncio.run(get_model_info(...))
     —— 每个 lora 新建/销毁一个事件循环（线程池里 asyncio.run 反模式），
     而外层 get_extra_networks 本来就是协程，完全可以直接 await。
  2. preview_file() 每次请求都对每张封面做 PIL 解码+缩放+base64，
     纯 CPU 阻塞（本机 151 个 lora，每刷一次面板全部重来）。
  3. download_image 用同步 requests 直接打图床，容易堵事件循环。

改法：真 async 并发（asyncio.gather + Semaphore(8)）；封面缩略图丢
run_in_executor 并按 (封面路径, mtime_ns, size) 键做进程内缓存（文件没
被动过就永不重算）。返回 JSON 的字段结构（顶层 [{name,title,items}] 与
item 各字段）与前端 prompt_js/main.entry.js 现契约完全一致，没有改成方案
文档里的分页新形状（前端是打包产物不可改）。auto_fetch 参数语义不变。
"""
import os
import sys
import folder_paths
from PIL import Image
import base64
from io import BytesIO
from pathlib import Path
import requests
import asyncio
import functools

Path = os.path.join(os.path.dirname(__file__), "../../../../")
sys.path.append(Path)
from script.lorainfo import get_model_info

filters = [
    # 'filename',
    # 'description',
    'search_term',
    'local_preview',
    'metadata',
]

def quote_js(s):
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    return f'"{s}"'

def download_image(url, filename, directory):
    _, ext = os.path.splitext(url)
    filename, _ = os.path.splitext(filename)
    filepath = os.path.join(directory, f"{filename}{ext}")
    try:
        resp = requests.get(url, stream=True)
        resp.raise_for_status()
        with open(filepath, 'wb') as f:
             for chunk in resp.iter_content(chunk_size=4096):
                 f.write(chunk)
    except Exception as e:
        print(e)
        if os.path.exists(filepath):
            os.remove(filepath)

async def prepare_lora_item_data(item_path, auto_fetch=False):
    """组装单个 lora 的面板 item。[P1-3] 由「线程池函数里 asyncio.run」改为
    协程直接 await —— get_model_info 内部的同步阻塞 IO 已在 lorainfo.py 里
    包进 run_in_executor，这里不再需要自建事件循环。"""
    loop = asyncio.get_running_loop()
    lora_path = folder_paths.get_full_path("loras", item_path)
    [model_name, model_extension] = os.path.splitext(item_path)
    file_name = os.path.basename(item_path)
    info_data = await get_model_info(item_path, light=True)
    if auto_fetch:
        if len(info_data['images']) == 0: # 无数据
            info_data = await get_model_info(item_path, maybe_fetch_civitai=True, maybe_fetch_metadata=True, light=False)
        if len(info_data['images']) != 0 and item_path not in info_data['images'][0]['url']: # 未设置封面
            url = next(filter(lambda x: x['type'] == 'image', info_data['images']), {}).get('url')
            # [P1-3] requests 流式下载是阻塞 IO，丢线程池执行，不挡事件循环。
            await loop.run_in_executor(None, functools.partial(
                download_image, url=url, filename=file_name,
                directory=os.path.dirname(lora_path)))

    # [P1-3] 封面缩略图（PIL 解码+缩放+base64，CPU 密集）丢线程池；
    # preview_file 内部自带按 (封面路径, mtime_ns, size) 的进程内缓存。
    preview = await loop.run_in_executor(None, preview_file, lora_path)

    item = {
            "basename": item_path,
            "name": item_path,
            "dirname": os.path.dirname(lora_path),
            "filename": lora_path,
            "description": "",
            "preview":preview,
            "model_name": model_name,
            "model_type": "loras",
            "model_filename": file_name,
            # "shorthash": lora_on_disk.shorthash,
            # "preview": self.find_preview(path),
            # "description": self.find_description(path),
            # "search_terms": search_terms,
            # "local_preview": f"{path}.{shared.opts.samples_format}",
            # "metadata": lora_on_disk.metadata,
            # "sort_keys": {'default': index, **self.get_sort_keys(lora_on_disk.filename)},
            # "sd_version": lora_on_disk.sd_version.name,
        }
    # item["prompt"] = quote_js(f"<lora:{item_path}:1") + quote_js(">")
    item["prompt"] = f"<lora:{item_path}:"
    item["local_info"] = info_data
    # item["search_terms"] = ["Lora\\"+item_path]
    return item

async def get_extra_networks(auto_fetch=False):
    loras_path  = folder_paths.get_filename_list("loras")
    result = []
    result_item = {
        'name': "lora",
        'title': "Lora",
        'items': []
    }
    # [P1-3] 删掉「线程池里每个 lora 跑 asyncio.run」的反模式：同一事件循环
    # 内 asyncio.gather 真并发，Semaphore(8) 限流磁盘/网络并发，防把 IO 打满。
    sem = asyncio.Semaphore(8)

    async def one(item_path):
        async with sem:
            try:
                return await prepare_lora_item_data(item_path, auto_fetch)
            except Exception as e:
                # 单个 lora 出错只丢该项；原实现 future.result() 会把第一个
                # 异常抛穿到路由层导致整个面板请求 500，这里更稳。
                print(f"[WeiLin] extra_networks 跳过 {item_path}: {e}")
                return None

    gathered = await asyncio.gather(*(one(p) for p in loras_path))
    items = [it for it in gathered if it is not None]
    result_item['items'] = items
    result.append(result_item)
    return result

PREVIEW_EXTS = [".jpg", ".png", ".jpeg", ".gif"]
PREVIEW_EXTS = [*PREVIEW_EXTS, *[".preview" + x for x in PREVIEW_EXTS]]

# [P1-3] 封面缩略图进程内缓存：key=(封面路径, mtime_ns, size)。
# 封面没被改过就永不重算（PIL+base64 是纯 CPU 活）；mtime/size 变了自然
# miss 重算；旧条目靠下面的容量上限整体淘汰，不会无限涨。
_preview_cache = {}
_PREVIEW_CACHE_MAX = 2048


def _find_preview_path(filename: str):
    """返回 lora 旁边第一张存在的封面/预览图路径（扩展名顺序即优先级）。"""
    for ext in PREVIEW_EXTS:
        try:
            pathStr = os.path.splitext(filename)[0] + ext
            if os.path.exists(pathStr):
                return pathStr
        except Exception as e:
            print(f"读取封面出错: {e}")
            return None
    return None


def preview_file(filename: str):
    # because ComfyUI has extra model path feature
    # the path might not be relative to the ComfyUI root
    # so instead of returning the path, we return the image data directly, to avoid security issues
    try:
        pathStr = _find_preview_path(filename)
        if pathStr is None:
            return None
        st = os.stat(pathStr)
        key = (pathStr, st.st_mtime_ns, st.st_size)   # 文件没动 -> 缓存必命中
        if key in _preview_cache:
            return _preview_cache[key]
        bytes = get_thumbnail_for_image_file(pathStr)
        if bytes is None:
            return None
        # Get the base64 string（'base64, ' 逗号后的空格属原契约格式，勿改）
        img_base64 = base64.b64encode(bytes).decode()
        value = f"data:image/jpeg;base64, {img_base64}"
        if len(_preview_cache) >= _PREVIEW_CACHE_MAX:
            _preview_cache.clear()   # 简单容量上限，防封面频繁增删导致内存漂移
        _preview_cache[key] = value
        return value
    except Exception as e:
        print(f"读取封面出错: {e}")
        return None


MAX_IMAGE_SIZE = 250

def get_thumbnail_for_image_file(file_path):
    try:
        with Image.open(file_path) as img:
            # If the image is too large, resize it
            if img.width > MAX_IMAGE_SIZE and img.height > MAX_IMAGE_SIZE:
                # Calculate new width to maintain aspect ratio
                width = int(img.width * MAX_IMAGE_SIZE / img.height)
                # Resize the image
                img = img.resize((width, MAX_IMAGE_SIZE))
            img = img.convert("RGB")
            # Save the image to a BytesIO object
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            return buffer.getvalue()
    except Exception as e:
        print(f"打开封面出错: {e}")
        return None
