import random

from loguru import logger

from . import files, pathes

logger.info(f"Загружен модуль {__name__}!")


async def add(ticket_id: int | str, value: int | str) -> str:
    def _updater(data: dict) -> str:
        available_ids = set(map(str, range(1000, 10000))) - data.keys()
        if not available_ids:
            msg = "Нет доступных ID для чеков. Пожалуйста, удалите старые чеки."
            raise ValueError(msg)

        random_id = random.choice(tuple(available_ids))
        data[random_id] = {"author": int(ticket_id), "value": int(value)}
        return random_id

    return await files.update_json_async(pathes.tickets, _updater, indent=True)


async def pop(ticket_id):
    """Атомарно возвращает и удаляет чек.

    Возвращает данные чека или None, если такого ID нет. Благодаря
    удержанию лока на время операции чек нельзя активировать дважды.
    """
    key = str(ticket_id)

    def _updater(data: dict):
        return data.pop(key, None)

    return await files.update_json_async(pathes.tickets, _updater, indent=True)
