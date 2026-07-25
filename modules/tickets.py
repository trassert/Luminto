import random

from loguru import logger

from . import files, pathes

logger.info(f"Загружен модуль {__name__}!")


async def get(ticket_id):
    if not pathes.tickets.exists():
        await files.save_json_async(pathes.tickets, {})
        return None
    data = await files.load_json_async(pathes.tickets)
    return data.get(str(ticket_id), None)


async def add(ticket_id: int | str, value: int | str) -> str:
    data = await files.load_json_async(pathes.tickets)

    available_ids = set(map(str, range(1000, 10000))) - data.keys()
    if not available_ids:
        msg = "Нет доступных ID для чеков. Пожалуйста, удалите старые чеки."
        raise ValueError(msg)

    random_id = random.choice(tuple(available_ids))
    data[random_id] = {"author": int(ticket_id), "value": int(value)}

    await files.save_json_async(pathes.tickets, data, indent=True)
    return random_id


async def delete(ticket_id):
    data = await files.load_json_async(pathes.tickets)
    if ticket_id not in data:
        return None
    del data[ticket_id]
    await files.save_json_async(pathes.tickets, data, indent=True)
    return True
