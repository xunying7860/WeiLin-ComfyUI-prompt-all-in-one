import sys
import os

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
from get_i18n import get_i18n


def replace_vars(text, vars):
    for key, value in vars.items():
        text = text.replace("{" + key + "}", value)
    return text


def get_lang(key, vars={}):
    i18n = get_i18n()
    code = storage.get('languageCode')

    def find_lang(code):
        for item in i18n['languages']:
            if item['code'] == code:
                return True
        return False

    if not find_lang(code):
        code = i18n['default']

    if not find_lang(code):
        code = 'en_US'

    def find_key(key, code):
        for item in i18n['languages']:
            if item['code'] == code:
                if key in item['lang']:
                    if vars == {}:
                        return item['lang'][key]
                    else:
                        return replace_vars(item['lang'][key], vars)
        return False

    find = find_key(key, code)
    if find:
        return find

    find = find_key(key, 'en_US')
    if find:
        return find

    return replace_vars(key, vars)
