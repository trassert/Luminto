from loguru import logger

from . import db, pathes, files

logger.info(f"Загружен модуль {__name__}!")


async def get(id: str) -> int:
    id = str(id)
    data = await files.load_json_async(pathes.crocostat)
    if id in data:
        return data[id]
    data[id] = 0
    await files.save_json_async(pathes.crocostat, data, sort_keys=True)
    return 0


async def add(id: str) -> None:
    id = str(id)
    data = await files.load_json_async(pathes.crocostat)
    data[id] = data.get(id, 0) + 1
    await files.save_json_async(pathes.crocostat, data, sort_keys=True)


async def get_all():
    data = await files.load_json_async(pathes.crocostat)
    return dict(sorted(data.items(), key=lambda item: item[1], reverse=True))
