from pathlib import Path
from typing import TypedDict

from loguru import logger

from . import files, pathes

logger.info(f"Загружен модуль {__name__}")

pathes.notes.mkdir(exist_ok=True, parents=True)


class Note(TypedDict):
    author: int
    text: str


def _get_file_path(name: str) -> Path:
    return pathes.notes / f"{name.lower()}.json"


async def get(name: str) -> Note | None:
    """Получить заметку по имени."""
    file_path = _get_file_path(name.lower())
    if not file_path.exists():
        return None

    try:
        data = await files.load_json_async(file_path)
        return Note(author=data["author"], text=data["text"])
    except (KeyError, ValueError) as e:
        logger.error(f"Ошибка чтения заметки {name}: {e}")
        return None


async def create(author_id: int, name: str, text: str) -> bool:
    """Создать новую заметку с указанным автором."""
    file_path = _get_file_path(name.lower())
    if file_path.exists():
        return False

    note_data: Note = {"author": author_id, "text": text}
    await files.save_json_async(file_path, note_data, indent=True)
    return True


async def remove(name: str) -> bool:
    """Удалить заметку по имени."""
    file_path = _get_file_path(name.lower())
    return await files.remove_file_async(file_path)


def get_all() -> list[str]:
    """Получить список всех имён заметок."""
    if not pathes.notes.exists():
        return []
    return [
        f.stem
        for f in pathes.notes.iterdir()
        if f.is_file() and f.suffix == ".json"
    ]


async def get_by_author(author_id: int) -> list[tuple[str, str]]:
    """Получить все заметки конкретного автора."""
    if not pathes.notes.exists():
        return []

    result = []
    all_notes = get_all()
    for name in all_notes:
        note = await get(name)
        if note and note["author"] == author_id:
            result.append(name)
    return result
