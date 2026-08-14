import asyncio
from pathlib import Path

import aiofiles
import anyio
import orjson


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


def load_json_sync(filepath: Path) -> dict:
    """Загружает JSON файл синхронно."""
    with filepath.open("rb") as f:
        raw = f.read()
    return orjson.loads(raw)


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
    ensure_parent(filepath)
    lock = await get_lock(filepath)
    options = orjson_options(sort_keys=sort_keys, indent=indent)
    dump = orjson.dumps(data, option=options)
    async with lock:
        async with aiofiles.open(filepath, "wb") as f:
            return await f.write(dump)


async def load_text_async(filepath: Path) -> str:
    """Загружает текстовый файл асинхронно."""
    lock = await get_lock(filepath)
    async with lock:
        async with aiofiles.open(filepath, encoding="utf-8") as f:
            return await f.read()


async def save_text_async(filepath: Path, text: str):
    """Сохраняет текстовый файл асинхронно."""
    ensure_parent(filepath)
    lock = await get_lock(filepath)
    async with lock:
        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            return await f.write(text)


async def remove_file_async(filepath: Path):
    """Удаляет файл асинхронно."""
    if not filepath.exists():
        return False
    await anyio.Path(filepath).remove()
    return True
