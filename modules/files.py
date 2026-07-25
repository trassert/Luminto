import asyncio
from pathlib import Path

import aiofiles
import anyio
import orjson


def load_json_sync(filepath: Path) -> dict:
    """Загружает JSON файл синхронно."""
    with filepath.open("rb") as f:
        raw = f.read()
    return orjson.loads(raw)


def orjson_options(sort_keys: bool = False, indent: bool = False) -> int:
    opts = 0
    if sort_keys:
        opts |= orjson.OPT_SORT_KEYS
    if indent:
        opts |= orjson.OPT_INDENT_2
    return opts


def ensure_parent(filepath: Path) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)


def save_json_sync(
    filepath: Path,
    data: dict,
    sort_keys: bool = False,
    indent: bool = False,
):
    """Сохраняет JSON файл синхронно."""
    ensure_parent(filepath)
    options = orjson_options(sort_keys=sort_keys, indent=indent)
    with filepath.open("wb") as f:
        f.write(orjson.dumps(data, option=options))


_file_locks: dict[str, asyncio.Lock] = {}
_locks_lock = asyncio.Lock()


async def get_lock(filepath: Path) -> asyncio.Lock:
    path_str = str(await anyio.Path(filepath).resolve())
    async with _locks_lock:
        if path_str not in _file_locks:
            _file_locks[path_str] = asyncio.Lock()
        return _file_locks[path_str]


async def load_json_async(filepath: Path) -> dict:
    """Загружает JSON файл асинхронно."""
    lock = await get_lock(filepath)
    async with lock:
        async with aiofiles.open(filepath, "rb") as f:
            raw = await f.read()
    return orjson.loads(raw)


async def save_json_async(
    filepath: Path,
    data: dict,
    sort_keys: bool = False,
    indent: bool = False,
):
    """Сохраняет JSON файл асинхронно."""
    lock = await get_lock(filepath)
    options = orjson_options(sort_keys=sort_keys, indent=indent)
    dump = orjson.dumps(data, option=options)
    async with lock:
        ensure_parent(filepath)
        async with aiofiles.open(filepath, "wb") as f:
            return await f.write(dump)
