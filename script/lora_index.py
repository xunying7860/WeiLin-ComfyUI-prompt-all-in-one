# -*- coding: utf-8 -*-
"""
lora_index.py — lora 采样指纹索引（方案 B1/B2/B8、P1-2/P1-3）
==============================================================
解决的问题（实测口径见方案文档 §B1）：
  script/lorainfo.py 原来对每个 lora 做「全文件 4KB 逐块 sha256」，
  本机 models/loras 有 151 个文件（含 2.36GB 大文件），且这段代码
  直接跑在 aiohttp 事件循环里 —— 期间整个 ComfyUI 卡死。

落地做法（三层）：
  A. 采样指纹：size + 头/中/尾各 1MB -> blake2b-128。单文件从「读整库」
     变成「读 3MB」，快 ~60 倍以上；civitai 的 by-hash 缓存场景碰撞可忽略。
  B. 指纹落 SQLite（进程重启不重算）+ 进程内 dict 双缓存。
     连接 check_same_thread=False 且读写全部持锁 —— 预热线程与 aiohttp
     路由线程会并发访问同一个连接。
  C. 启动时后台预热（__init__.py 末尾调 warmup_loras_background），
     用户点开 Lora 面板时指纹已经是热的。

对外契约（__init__.py 钩子与 lorainfo.py 依赖）：
  init(userdata_dir)                       —— 指定 sqlite 落盘目录
  get_file_hash(path, exact=False) -> str  —— drop-in 替换 _get_sha256_hash；
      path 为 None / 不存在时返回 ""（静默容错，预热列表里可能有 None）
  warmup_loras_background(paths, exact=False) —— 非阻塞排线程池
  full_sha256(path)                        —— 精确 sha256（仅 civitai 查询用）

注意：exact=True 是纯阻塞 IO（可能读 2GB+），事件循环里调用方必须
自行包 loop.run_in_executor —— 本模块不自带 async 承诺。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
import threading
import time

_SAMPLE = 1024 * 1024          # 头/中/尾各采样 1MB
_DB_LOCK = threading.Lock()    # sqlite 连接读写锁（预热线程 vs 路由线程）
_DB: sqlite3.Connection | None = None
_DB_PATH = ""                  # init() 设置；未 init 时懒加载兜底路径
# path -> (mtime, size, 采样指纹, 精确sha256[可空])。fp/sha 分开存：
# exact 与非 exact 调用互不污染返回值。
_mem: dict[str, tuple[float, int, str, str]] = {}


# ------------------------------------------------------------------ 采样指纹
def sample_fingerprint(path: str) -> str:
    """只读 3MB（头/中/尾各 1MB + size）得到指纹，代替全文件 sha256。"""
    size = os.path.getsize(path)
    h = hashlib.blake2b(digest_size=16)
    h.update(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(_SAMPLE))
        if size > _SAMPLE * 2:
            # 中等以下文件整体已被首块覆盖，无需再 seek，省随机读。
            f.seek(size // 2)
            h.update(f.read(_SAMPLE))
            f.seek(max(0, size - _SAMPLE))
            h.update(f.read(_SAMPLE))
    return h.hexdigest()


def full_sha256(path: str) -> str:
    """精确 sha256。只在真正需要（civitai by-hash 查询 / 用户手动 refresh）
    时用，且调用方若在事件循环里必须放线程池（run_in_executor）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        # 1MB 一块：比原来 4KB 少 256 倍系统调用，纯内存 sha256 吞吐不变
        for blk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(blk)
    return h.hexdigest()


# ------------------------------------------------------------------ 缓存层
def _default_db_path() -> str:
    """init() 没被调用时的兜底：插件根/lora_userdata（与 __init__.py 钩子一致）。"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "lora_userdata", "lora_index.sqlite3")


def _db() -> sqlite3.Connection:
    """取得（并按需创建）sqlite 连接。必须在持有 _DB_LOCK 时调用。"""
    global _DB
    if _DB is None:
        path = _DB_PATH or _default_db_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except OSError:
            pass
        # check_same_thread=False：预热线程与 aiohttp 路由共用一个连接，
        # 所有读写在 _DB_LOCK 下串行，杜绝交叉事务。
        _DB = sqlite3.connect(path, check_same_thread=False)
        _DB.execute("""CREATE TABLE IF NOT EXISTS fp (
                           path TEXT PRIMARY KEY, mtime REAL, size INTEGER,
                           fp TEXT, sha TEXT)""")
        _DB.commit()
    return _DB


def init(userdata_dir: str) -> None:
    """__init__.py 钩子调用：指定索引 sqlite 的落盘目录。"""
    global _DB_PATH, _DB
    os.makedirs(userdata_dir, exist_ok=True)
    _DB_PATH = os.path.join(userdata_dir, "lora_index.sqlite3")
    with _DB_LOCK:
        _DB = None      # 下次用时按新路径重建


def get_file_hash(path, exact: bool = False) -> str:
    """
    drop-in 替换 lorainfo._get_sha256_hash(file_path)。
    exact=False -> 采样指纹（默认，读 3MB，事件循环里可直接调）
    exact=True  -> 精确 sha256（结果入库，下次命中；调用方若在事件循环
                   必须自行 run_in_executor）
    path 为 None / 文件不存在 -> 返回 ""（静默容错）。

    ⚠ 修正了参考补丁 02 的一处缺陷：原补丁在「库里只存过 fp」时把 fp
    当作 exact 结果返回（fp≠sha256，拿去打 civitai by-hash 会 404）。
    这里 fp/sha 分开判：exact 缺 sha 时补算 sha 并回写，fp 保留不丢。
    """
    try:
        st = os.stat(path)          # path=None 时抛 TypeError，一并吞掉
    except (TypeError, ValueError, OSError):
        return ""

    fp = sha = ""
    e = _mem.get(path)
    if e and e[0] == st.st_mtime and e[1] == st.st_size:
        # 进程内一级缓存：mtime/size 未变即命中，微秒级
        fp, sha = e[2], e[3]
        if (not exact and fp) or (exact and sha):
            return fp if not exact else sha
    elif not e:
        with _DB_LOCK:             # 二级缓存：sqlite（重启后不重算）
            db = _db()
            row = db.execute("SELECT mtime, size, fp, sha FROM fp WHERE path=?",
                             (path,)).fetchone()
        if row and row[0] == st.st_mtime and row[1] == st.st_size:
            fp, sha = row[2], row[3]

    if not fp:                     # 冷计算：3MB 采样指纹
        fp = sample_fingerprint(path)
    if exact and not sha:          # 冷计算：全文件 sha256（调用方须离线循环）
        sha = full_sha256(path)

    _mem[path] = (st.st_mtime, st.st_size, fp, sha)
    with _DB_LOCK:
        db = _db()
        db.execute("INSERT OR REPLACE INTO fp VALUES (?,?,?,?,?)",
                   (path, st.st_mtime, st.st_size, fp, sha))
        db.commit()
    return sha if exact else fp


# ------------------------------------------------------------------ 后台预热
def warmup_loras_background(lora_paths, exact: bool = False):
    """
    ComfyUI 启动后把 lora 指纹在后台线程算完（非阻塞，立即返回），
    用户点开 Lora 面板时已经是热的。列表里允许混入 None（get_full_path
    失败会产生 None），get_file_hash 已静默容错。
    """
    def _run():
        t0 = time.perf_counter()
        n = 0
        for p in lora_paths:
            try:
                if get_file_hash(p, exact=exact):
                    n += 1
            except Exception:
                pass
        print(f"[WeiLin] lora index warmup done: {n}/{len(lora_paths)} files in "
              f"{time.perf_counter()-t0:.1f}s")

    threading.Thread(target=_run, name="weilin-lora-warmup", daemon=True).start()


async def awarmup_loras(lora_paths, exact: bool = False):
    """async 版本：限制并发为 4，避免把磁盘打满影响出图。"""
    sem = asyncio.Semaphore(4)
    loop = asyncio.get_running_loop()

    async def one(p):
        async with sem:
            await loop.run_in_executor(None, get_file_hash, p, exact)

    await asyncio.gather(*(one(p) for p in lora_paths), return_exceptions=True)
