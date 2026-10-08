import os
import sys

# 修复个别电脑环境会报的错
Path = os.path.dirname(__file__)
sys.path.append(Path)

# 修复(2026-10)：ComfyUI 新增了 comfy/storage.py，且 nodes.py 把 <ComfyUI>/comfy 插到 sys.path 最前面，
# 于是裸 `from storage import Storage` 会命中 ComfyUI 的同名模块并报 ImportError。
# 改为包限定导入（与 scripts/on_app_started.py 的写法一致），不再依赖 sys.path 顺序。
try:
    from physton_prompt.storage import Storage
except ImportError:
    # 兜底：以 scripts.physton_prompt.* 或裸模块方式加载时仍可用
    from storage import Storage

storage = Storage()

styles_path = os.path.join(os.path.dirname(__file__), "../../../../prompt_static/styles")
styles_path = os.path.normpath(styles_path)

def get_style_full_path(file):
    global styles_path
    path = os.path.join(styles_path, file)
    path = os.path.abspath(path)
    path = os.path.normpath(path)
    if not os.path.exists(path):
        return None
    if styles_path not in path:
        return None
    return path


def get_extension_css_list():
    global styles_path
    extension_path = os.path.join(styles_path, 'extensions')
    if not os.path.exists(extension_path):
        return []
    css_list = []
    # 扫描下面的每个文件夹
    for dir in os.listdir(extension_path):
        dir_path = os.path.join(extension_path, dir)
        if not os.path.isdir(dir_path):
            continue

        # 是否有 manifest.json 文件
        manifest_path = os.path.join(dir_path, 'manifest.json')
        if not os.path.exists(manifest_path):
            continue

        # 是否有 style.min.css 文件
        style_path = os.path.join(dir_path, 'style.min.css')
        if not os.path.exists(style_path):
            continue

        manifest = None
        try:
            with open(manifest_path, 'r', encoding='utf8', errors='ignore') as f:
                manifest = f.read()
        except Exception as e:
            print(f'读取 {manifest_path} 失败：{e}')
            pass
        if not manifest:
            continue

        css_item = {
            'dir': dir,
            'dataName': 'extensionSelect.' + dir,
            'selected': False,
            'manifest': manifest,
            'style': f'extensions/{dir}/style.min.css',
        }
        css_item['selected'] = storage.get(css_item['dataName'])
        css_list.append(css_item)

    return css_list
