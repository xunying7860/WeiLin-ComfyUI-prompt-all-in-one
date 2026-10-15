"""
get_group_tags.py —— group tags 读写模块（快版）
=================================================
替换旧版 ruamel.yaml 实现：旧版每次读都要 round-trip 解析 228 KB 的 zh_CN.yaml
（方案文档 §B3 实测 619 ms），改一个 tag 要 load+dump 写回整个文件（966 ms，
同步阻塞 aiohttp 事件循环，期间整个 ComfyUI 无响应）。

设计要点（对照补丁 01_fast_group_tags.py 与方案 §B3/B4）：
  1. 读路径 get_group_tags 保持同步函数：拼接顺序与旧版完全一致
     （prepend + main + append，各段之间以 \\n\\n 连接），返回值与旧版一致。
     main 文件选择顺序与旧版一致：custom(非空) > lang > default；
     main 不存在时直接返回 ''（即使 prepend/append 存在），保持旧行为。
     用 1 秒 TTL 快照缓存：热路径连 stat 系统调用都是 0 次
     （某些文件系统/网络盘上 stat 可达数 ms 一次，必须连 stat 一起省掉）。
  2. 写路径（9 个增删改函数）改为协程：load -> 改 -> dump -> os.replace 原子写，
     整段丢进 run_in_executor，不再阻塞 ComfyUI 事件循环；断电不会留下半文件。
  3. 公开 API 与旧版同名同参同返回；唯一区别是增删改函数现在是协程，
     路由里必须 await（on_app_started.py 已适配）。
  4. 依赖 PyYAML：优先用 libyaml C 扩展（CSafeLoader/CDumper，比纯 Python
     快约 20 倍）；没有 C 扩展时退回 SafeLoader/Dumper，仍远快于 ruamel。
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from hashlib import md5

import yaml

# 优先 PyYAML 的 C 实现（libyaml）；装的是纯 Python wheel 时退回纯 Python 解析器
try:
    from yaml import CSafeLoader as _SafeLoader, CDumper as _Dumper
except ImportError:
    from yaml import SafeLoader as _SafeLoader, Dumper as _Dumper

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# 与旧文件实测深度一致：scripts/physton_prompt 往上 4 层即插件根，group_tags/ 在根下
# （旧文件写法 os.path.join(current_dir, '../../../../group_tags/', name + '.yaml')）
_TAGS_DIR = os.path.normpath(os.path.join(_CURRENT_DIR, "../../../../group_tags/"))

# 快照缓存有效期（秒）。tag 库是低频变更数据，1 秒足够。
_SNAPSHOT_TTL = 1.0

_RAW_CACHE: dict[str, tuple[float, int, str]] = {}          # fp -> (mtime, size, text)
_PARSE_CACHE: dict[str, tuple[float, int, object]] = {}     # fp -> (mtime, size, data)
_TEXT_CACHE: dict[str, tuple[float, str]] = {}              # lang -> (sig, text)
_SNAPSHOT: dict[str, tuple[float, list[str], float, str]] = {}  # lang -> (expire, files, sig, main_fp)
_LOCK = threading.Lock()
_WRITE_LOCK = threading.Lock()          # 写操作串行，避免并发互相覆盖


# ------------------------------------------------------------------ 基础工具
def _tags_file(name: str) -> str:
    """等价于旧版 _get_tags_filename：<插件根>/group_tags/<name>.yaml"""
    return os.path.join(_TAGS_DIR, f"{name}.yaml")


def _stat(fp: str):
    st = os.stat(fp)
    return st.st_mtime, st.st_size


def _read_cached(fp: str) -> str:
    """带 mtime/size 校验的文本缓存：文件没变就不重新读。"""
    mtime, size = _stat(fp)
    hit = _RAW_CACHE.get(fp)
    if hit is not None and hit[0] == mtime and hit[1] == size:
        return hit[2]
    with open(fp, "r", encoding="utf-8") as f:
        data = f.read()
    _RAW_CACHE[fp] = (mtime, size, data)
    return data


_CUSTOM_STATE = {"mtime": -1.0, "exists": False}


def _custom_exists() -> bool:
    """旧行为：custom.yaml 存在且非空才使用；旧实现每次请求 open+read，这里按 mtime 缓存。"""
    fp = _tags_file("custom")
    try:
        mtime = _stat(fp)[0]
    except OSError:
        return False
    if _CUSTOM_STATE["mtime"] == mtime:
        return _CUSTOM_STATE["exists"]
    try:
        with open(fp, "r", encoding="utf8") as f:
            exists = len(f.read().strip()) > 0
    except OSError:
        exists = False
    _CUSTOM_STATE.update(mtime=mtime, exists=exists)
    return exists


def _resolve_main_file(lang: str):
    """旧版 main 文件选择顺序：custom(非空) > lang > default；都不存在返回 None。"""
    if _custom_exists():
        return _tags_file("custom")
    fp = _tags_file(lang)
    if os.path.exists(fp):
        return fp
    fp = _tags_file("default")
    if os.path.exists(fp):
        return fp
    return None


def _snapshot(lang: str):
    """
    返回 (files, sig, main_fp)：
      files   —— [prepend, main, append] 中实际存在的文件，按拼接顺序；
      sig     —— 所有文件 mtime 之和，作文本缓存键（任一文件变了就重算）；
      main_fp —— 主文件路径或 None（None 时 get_group_tags 必须返回 ''）。
    带 1 秒 TTL —— 热路径 0 系统调用。
    """
    now = time.monotonic()
    hit = _SNAPSHOT.get(lang)
    if hit is not None and hit[0] > now:
        return hit[1], hit[2], hit[3]

    files: list[str] = []
    fp = _tags_file("prepend")
    if os.path.exists(fp):
        files.append(fp)
    main_fp = _resolve_main_file(lang)
    if main_fp is not None:
        files.append(main_fp)
    fp = _tags_file("append")
    if os.path.exists(fp):
        files.append(fp)

    sig = sum(_stat(fp)[0] for fp in files)
    _SNAPSHOT[lang] = (now + _SNAPSHOT_TTL, files, sig, main_fp)
    return files, sig, main_fp


# ------------------------------------------------------------------ 读路径
def get_group_tags(lang: str) -> str:
    """
    公开 API 与旧版完全一致（同步函数、同返回）：
    prepend + main + append 拼成的字符串（各段以 \\n\\n 连接，末尾多一个 \\n\\n）。
    旧行为保留：main 文件不存在时直接返回 ''（即使 prepend/append 存在）。
    """
    files, sig, main_fp = _snapshot(lang)
    if main_fp is None or not files:
        return ""
    hit = _TEXT_CACHE.get(lang)
    if hit is not None and hit[0] == sig:
        return hit[1]
    text = "\n\n".join(_read_cached(fp) for fp in files) + "\n\n"
    _TEXT_CACHE[lang] = (sig, text)
    return text


def get_group_tags_etag(lang: str) -> str:
    """新增辅助接口（不属于旧 API）：给路由算 ETag，前端带 If-None-Match 时可回 304。"""
    files, sig, _main = _snapshot(lang)
    return '"%s"' % md5(("%.6f|" % sig).encode() + "|".join(files).encode()).hexdigest()


def load_tags(lang: str):
    """
    新增辅助接口（不属于旧 API）：解析后的结构化 tag 树（为未来的 SQLite/搜索索引预留）。
    只解析主文件（不是 prepend/append），main 不存在返回 None。
    """
    _files, _sig, main_fp = _snapshot(lang)
    if main_fp is None:
        return None
    mtime, size = _stat(main_fp)
    hit = _PARSE_CACHE.get(main_fp)
    if hit is not None and hit[0] == mtime and hit[1] == size:
        return hit[2]
    with _LOCK:
        data = yaml.load(_read_cached(main_fp), Loader=_SafeLoader)
        _PARSE_CACHE[main_fp] = (mtime, size, data)
        return data


# ------------------------------------------------------------------ 写路径
def _atomic_write(fp: str, text: str) -> None:
    """先写临时文件再 os.replace 原子替换：断电不会留下半个文件；写后清掉读缓存。"""
    tmp = f"{fp}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, fp)                 # 原子替换
    _RAW_CACHE.pop(fp, None)
    _PARSE_CACHE.pop(fp, None)
    _TEXT_CACHE.clear()
    _SNAPSHOT.clear()


def _mutate(lang: str, fn) -> None:
    """
    同步阻塞版本：load -> 改 -> dump -> 原子写。
    禁止在事件循环里直接调用，必须走 _mutate_async（run_in_executor）。
    """
    fp = _tags_file(lang)
    if not os.path.exists(fp):
        raise FileNotFoundError(fp)
    with _WRITE_LOCK:
        data = yaml.load(_read_cached(fp), Loader=_SafeLoader)
        result = fn(data)
        if result is not None:          # fn 返回新列表时用于整体替换（deleteNodeGroup）
            data = result
        # width=100000 对齐旧 ruamel 实现，防止长 tag 行被自动换行；
        # allow_unicode 让中文原样输出；sort_keys=False 保持原有键序
        _atomic_write(fp, yaml.dump(data, Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=100000))


async def _mutate_async(lang: str, fn):
    """关键：把同步写操作（旧版约 1 s）丢进线程池，不再卡死 ComfyUI 事件循环。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _mutate, lang, fn)


def _find_group(data, key, group_key):
    """按旧版语义定位 (key, group_key) 对应的 subgroup，找不到返回 None。"""
    for group in data:
        if group.get("name") == key:
            for sub in group["groups"]:
                if sub.get("name") == group_key:
                    return sub
    return None


# ------------------------------------------------------------------ 9 个增删改（均为协程，路由里 await）
async def addGroupTag(lang, cn, en, key, groupKey):
    """新增 tag：en -> cn。tag 值里带 ': ' 也不会像旧版 split(': ') 那样出错。"""
    def fn(data):
        sub = _find_group(data, key, groupKey)
        if sub is not None:
            sub.setdefault("tags", {})[en] = cn
    await _mutate_async(lang, fn)


async def editGroupTag(lang, cn, en, key, groupKey):
    """改 tag：仅当 en 键已存在时生效（旧版语义）。"""
    def fn(data):
        sub = _find_group(data, key, groupKey)
        if sub is not None and en in sub.get("tags", {}):
            sub["tags"][en] = cn
    await _mutate_async(lang, fn)


async def deleteGroupTag(lang, cn, en, key, groupKey):
    """删 tag：仅当 en 键已存在时生效（旧版语义）。"""
    def fn(data):
        sub = _find_group(data, key, groupKey)
        if sub is not None:
            sub.get("tags", {}).pop(en, None)
    await _mutate_async(lang, fn)


async def addNewNodeGroup(lang, key, groupKe, color):
    """新增顶级 group（含一个空 subgroup）。"""
    await _mutate_async(lang, lambda d: d.append(
        {"name": key, "groups": [{"name": groupKe, "color": color, "tags": {}}]}))


async def addNewGroup(lang, key, groupKe, color):
    """给目标顶级 group 新增 subgroup（第一个匹配的 group）。"""
    def fn(d):
        for g in d:
            if g.get("name") == key:
                g["groups"].append({"name": groupKe, "color": color, "tags": {}})
                return
    await _mutate_async(lang, fn)


async def editNodeGroup(lang, key, newKey):
    """重命名顶级 group（第一个匹配）。"""
    def fn(d):
        for g in d:
            if g.get("name") == key:
                g["name"] = newKey
                return
    await _mutate_async(lang, fn)


async def editChildNodeGroup(lang, key, groupA, newKey):
    """重命名 subgroup（第一个匹配）。"""
    def fn(d):
        for g in d:
            if g.get("name") == key:
                for sub in g["groups"]:
                    if sub.get("name") == groupA:
                        sub["name"] = newKey
                        return
    await _mutate_async(lang, fn)


async def deleteNodeGroup(lang, key):
    """删除顶级 group。"""
    await _mutate_async(lang, lambda d: [g for g in d if g.get("name") != key])


async def deleteChildNodeGroup(lang, key, groupKey):
    """删除目标 group 下所有叫 groupKey 的 subgroup（旧版反向迭代删除全部匹配）。"""
    def fn(d):
        for g in d:
            if g.get("name") == key:
                g["groups"] = [s for s in g["groups"] if s.get("name") != groupKey]
                return
    await _mutate_async(lang, fn)
