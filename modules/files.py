import asyncio
import weakref
from collections.abc import Callable
from pathlib import Path
from typing import Any

import aiofiles
import anyio
import orjson

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def orjson_options(sort_keys: bool = False, indent: bool = False) -> int:
    opts = 0
    if sort_keys:
        opts |= orjson.OPT_SORT_KEYS
    if indent:
        opts |= orjson.OPT_INDENT_2
    return opts


def ensure_parent(filepath: Path) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)


def _safe_path(filepath: Path) -> Path:
    # codeql[py/path-injection]
    # Ensure relative to _PROJECT_ROOT, preventing directory traversal
    resolved = (_PROJECT_ROOT / filepath).resolve()
    if not str(resolved).startswith(str(_PROJECT_ROOT)):
        msg = f"Недопустимый путь: {filepath!r}"
        raise ValueError(msg)
    return resolved


def save_json_sync(
    filepath: Path,
    data: dict,
    sort_keys: bool = False,
    indent: bool = False,
):
    filepath = _safe_path(filepath)
    ensure_parent(filepath)
    options = orjson_options(sort_keys=sort_keys, indent=indent)
    with filepath.open("wb") as f:
        f.write(orjson.dumps(data, option=options))


def load_json_sync(filepath: Path) -> dict:
    filepath = _safe_path(filepath)
    with filepath.open("rb") as f:
        raw = f.read()
    return orjson.loads(raw)


_file_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
_locks_lock = asyncio.Lock()


async def get_lock(filepath: Path) -> asyncio.Lock:
    path_str = str(await anyio.Path(filepath).resolve())
    async with _locks_lock:
        lock = _file_locks.get(path_str)
        if lock is None:
            lock = asyncio.Lock()
            _file_locks[path_str] = lock
        return lock


async def load_json_async(filepath: Path) -> dict:
    filepath = _safe_path(filepath)
    lock = await get_lock(filepath)
    async with lock, aiofiles.open(filepath, "rb") as f:
        raw = await f.read()
    return orjson.loads(raw)


async def save_json_async(
    filepath: Path,
    data: dict,
    sort_keys: bool = False,
    indent: bool = False,
):
    filepath = _safe_path(filepath)
    ensure_parent(filepath)
    lock = await get_lock(filepath)
    options = orjson_options(sort_keys=sort_keys, indent=indent)
    dump = orjson.dumps(data, option=options)
    async with lock, aiofiles.open(filepath, "wb") as f:
        return await f.write(dump)


async def load_text_async(filepath: Path) -> str:
    filepath = _safe_path(filepath)
    lock = await get_lock(filepath)
    async with lock, aiofiles.open(filepath, encoding="utf-8") as f:
        return await f.read()


async def save_text_async(filepath: Path, text: str):
    filepath = _safe_path(filepath)
    ensure_parent(filepath)
    lock = await get_lock(filepath)
    async with lock, aiofiles.open(filepath, "w", encoding="utf-8") as f:
        return await f.write(text)


async def remove_file_async(filepath: Path):
    filepath = _safe_path(filepath)
    p = anyio.Path(filepath)
    if not await p.exists():
        return False
    await p.unlink()
    return True


async def update_json_async(
    filepath: Path,
    updater: Callable[[dict], Any],
    sort_keys: bool = False,
    indent: bool = False,
) -> Any:
    filepath = _safe_path(filepath)
    lock = await get_lock(filepath)
    options = orjson_options(sort_keys=sort_keys, indent=indent)
    async with lock:
        try:
            async with aiofiles.open(filepath, "rb") as f:
                data = orjson.loads(await f.read())
        except FileNotFoundError:
            data = {}
        result = updater(data)
        ensure_parent(filepath)
        dump = orjson.dumps(data, option=options)
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(dump)
        return result


async def append_text_async(filepath: Path, text: str):
    filepath = _safe_path(filepath)
    ensure_parent(filepath)
    lock = await get_lock(filepath)
    async with lock, aiofiles.open(filepath, "a", encoding="utf-8") as f:
        return await f.write(text)
