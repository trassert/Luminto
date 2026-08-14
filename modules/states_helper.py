from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import anyio
from loguru import logger

from . import files, pathes

logger.info(f"Загружен модуль {__name__}")
def_dir = anyio.Path(pathes.states)
old_dir = anyio.Path(pathes.old_states)


async def add(state_name: str, author: int) -> bool:
    filepath = def_dir / f"{state_name}.json"
    if await filepath.is_file():
        return False
    today = datetime.now().strftime("%Y.%m.%d")
    data = {
        "price": 0,
        "enter": True,
        "desc": "Пусто",
        "players": [],
        "type": 0,
        "date": today,
        "money": 0,
        "author": author,
        "coordinates": "Не найдено",
        "tax": 0,
        "tax_period": 7,
        "tax_nonpayment": "nothing",
        "tax_last_date": today,
    }
    await files.save_json_async(filepath, data, indent=True)
    logger.info(f"Государство создано: {state_name}")
    return True


async def exists(state_name: str) -> bool:
    filepath = def_dir / f"{state_name}.json"
    return await filepath.is_file()


def count() -> int:
    """Количество существующих государств (синхронно)."""
    return len(list(pathes.states.glob("*.json")))


async def iter_states() -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Генератор пар (имя_государства, данные)."""
    async for file in (def_dir / "*.json").glob():
        try:
            data = await files.load_json_async(file)
            yield file.stem, data
        except Exception as e:
            logger.error(f"Не удалось загрузить гос-во {file.name}: {e}")


def _sort_key_money(item: tuple[str, dict[str, Any]]) -> int:
    return item[1].get("money", 0)


def _sort_key_players(item: tuple[str, dict[str, Any]]) -> int:
    return len(item[1].get("players", []))


async def get_all(sort_by: str = "players") -> dict[str, dict[str, Any]]:
    """Возвращает отсортированный словарь всех государств."""
    all_data = {name: data async for name, data in iter_states()}
    key_func = _sort_key_players if sort_by != "money" else _sort_key_money
    return dict(sorted(all_data.items(), key=key_func, reverse=True))


async def if_author(player_id: int) -> str | None:
    """Возвращает имя государства по ID автора или None."""
    async for name, data in iter_states():
        if data.get("author") == player_id:
            return name
    return None


async def if_player(player_id: int) -> str | None:
    """Возвращает имя государства, в котором состоит игрок, или None."""
    async for name, data in iter_states():
        if player_id in data.get("players", []):
            return name
    return None


async def remove(state_name: str) -> bool:
    """Перемещает файлы государства в архив (old_states)."""
    state_path = def_dir / f"{state_name}.json"
    if not await state_path.is_file():
        return False
    pic_path = anyio.Path(pathes.states_pic) / f"{state_name}.png"
    if await pic_path.is_file():
        await pic_path.rename(old_dir / f"{state_name}.png")
    await state_path.rename(old_dir / f"{state_name}.json")
    logger.info(f"Государство удалено в архив: {state_name}")
    return True
