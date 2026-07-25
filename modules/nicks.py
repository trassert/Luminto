from loguru import logger

from . import pathes, files

logger.info(f"Загружен модуль {__name__}!")


async def get_byid(id: int, if_nothing=None) -> str | None:
    data = await files.load_json_async(pathes.nick)
    return next(
        (k for k, v in data.items() if v == id), if_nothing
    )

async def get_byname(nick: str, if_nothing=None) -> int | None:
    data = await files.load_json_async(pathes.nick)
    nick_lower = nick.lower()
    return next(
        (v for k, v in data.items() if k.lower() == nick_lower),
        if_nothing,
    )

async def get_all() -> dict[str, int]:
    data = await files.load_json_async(pathes.nick)
    return dict(sorted(data.items()))


async def link(id: int, nick: str) -> bool:
    data = await files.load_json_async(pathes.nick)
    keys_to_remove = [k for k, v in data.items() if v == id]
    for k in keys_to_remove:
        del data[k]
    data[nick] = int(id)
    await files.save_json_async(pathes.nick, data, indent=True)
    return True
