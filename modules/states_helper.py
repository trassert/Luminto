from datetime import datetime
from typing import Any
from collections.abc import Iterator
from loguru import logger
from . import db, pathes

logger.info(f"Загружен модуль {__name__}")


def add(state_name: str, author: int) -> bool:
    filepath = pathes.states / f"{state_name}.json"
    if filepath.is_file():
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
    db._save_json_sync(filepath, data, indent=True)
    logger.info(f"Государство создано: {state_name}")
    return True


def exists(state_name: str) -> bool:
    """Проверяет существование государства (заменяет check и find)."""
    return (pathes.states / f"{state_name}.json").is_file()


def count() -> int:
    """Количество существующих государств."""
    return sum(1 for _ in pathes.states.glob("*.json"))


def iter_states() -> Iterator[tuple[str, dict[str, Any]]]:
    """Генератор пар (имя_государства, данные)."""
    for file in pathes.states.glob("*.json"):
        try:
            yield file.stem, db._load_json_sync(file)
        except Exception as e:
            logger.error(f"Не удалось загрузить гос-во {file.name}: {e}")


def get_all(sort_by: str = "players") -> dict[str, dict[str, Any]]:
    """Возвращает отсортированный словарь всех государств."""
    all_data = dict(iter_states())
    if sort_by == "money":

        def key_func(item):
            return item[1].get("money", 0)
    else:

        def key_func(item):
            return len(item[1].get("players", []))

    return dict(sorted(all_data.items(), key=key_func, reverse=True))


def get_state_by_author(player_id: int) -> str | None:
    """Возвращает имя государства по ID автора или None."""
    for name, data in iter_states():
        if data.get("author") == player_id:
            return name
    return None


def get_state_by_player(player_id: int) -> str | None:
    """Возвращает имя государства, в котором состоит игрок, или None."""
    for name, data in iter_states():
        if player_id in data.get("players", []):
            return name
    return None


def remove(state_name: str) -> bool:
    """Перемещает файлы государства в архив (old_states)."""
    state_path = pathes.states / f"{state_name}.json"
    if not state_path.is_file():
        return False
    pic_path = pathes.states_pic / f"{state_name}.png"
    if pic_path.is_file():
        pic_path.rename(pathes.old_states / f"{state_name}.png")
    state_path.rename(pathes.old_states / f"{state_name}.json")
    logger.info(f"Государство удалено в архив: {state_name}")
    return True
