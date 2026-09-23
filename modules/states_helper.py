from collections.abc import AsyncIterator
from datetime import datetime

import anyio
from loguru import logger

from . import config, db, files, nicks, pathes

logger.info(f"Загружен модуль {__name__}")
def_dir = anyio.Path(pathes.states)
old_dir = anyio.Path(pathes.old_states)


def _json(name: str):
    return pathes.states / f"{name}.json"


async def _dump(path, data):
    await files.save_json_async(path, data, indent=True, sort_keys=True)


class State:
    def __init__(self, name: str):
        self.name = name

    def __await__(self):
        return self._load().__await__()

    async def _load(self):
        self._data = await files.load_json_async(_json(self.name))
        s = config.cfg.States
        self._data.setdefault("tax", s.DefaultTax)
        self._data.setdefault("tax_period", s.DefaultTaxPeriod)
        self._data.setdefault("tax_nonpayment", s.DefaultTaxNonpayment)
        self._data.setdefault(
            "tax_last_date", datetime.now().strftime("%Y.%m.%d")
        )
        self._data.setdefault("recognition_votes", [])
        self._data.setdefault("recognition_pending", s.RecognitionPending)
        return self

    def __getattr__(self, key):
        return self._data[key]

    @property
    def is_recognized(self) -> bool:
        if self.type >= 1 or self.money >= 500:
            return True
        total = count()
        return total > 1 and len(self.recognition_votes) / (total - 1) > 0.5

    async def _save(self):
        await _dump(_json(self.name), self._data)

    async def change(self, key: str, value) -> None:
        if key == "players":
            value = list(value)
        self._data[key] = value
        await self._save()

    async def rename(self, new_name: str) -> bool:
        if await exists(new_name):
            return False
        await _dump(_json(new_name), self._data)
        await files.remove_file_async(_json(self.name))
        self.name = new_name
        return True

    async def pay_tax(self) -> dict:
        tax = int(self.tax or 0)
        if tax <= 0:
            return {"kicked": [], "payed": [], "collected": 0}
        payed, nonpayed, collected = [], [], 0
        for pid in list(self.players):
            if int(await db.get_money(pid) or 0) < tax:
                nonpayed.append(pid)
            else:
                await db.add_money(pid, -tax)
                payed.append(pid)
                collected += tax
        if collected:
            self._data["money"] = int(self.money or 0) + collected
        self._data["tax_last_date"] = datetime.now().strftime("%Y.%m.%d")
        kicked = []
        if nonpayed and self.tax_nonpayment == "kick":
            skip = set(nonpayed)
            kicked = [p for p in self.players if p in skip]
            self._data["players"] = [p for p in self.players if p not in skip]
            for pid in kicked:
                nick = await nicks.get_byid(pid) or pid
                logger.info(
                    f"{nick} ({pid}) кикнут из {self.name} за неуплату налогов."
                )
        await self._save()
        return {"kicked": kicked, "payed": payed, "collected": collected}

    async def remove(self) -> bool:
        money = int(self.money or 0)
        if money:
            await db.add_money(self.author, money)
        pic = anyio.Path(pathes.states_pic) / f"{self.name}.png"
        if await pic.is_file():
            await pic.rename(old_dir / f"{self.name}.png")
        await _dump(pathes.old_states / f"{self.name}.json", self._data)
        await files.remove_file_async(_json(self.name))
        logger.info(f"Государство удалено в архив: {self.name}")
        return True


async def add(state_name: str, author: int) -> bool:
    if await exists(state_name):
        return False
    today = datetime.now().strftime("%Y.%m.%d")
    s = config.cfg.States
    await _dump(
        _json(state_name),
        {
            "price": 0,
            "enter": True,
            "desc": "Пусто",
            "players": [],
            "type": 0,
            "date": today,
            "money": 0,
            "author": author,
            "coordinates": "Не найдено",
            "tax": s.DefaultTax,
            "tax_period": s.DefaultTaxPeriod,
            "tax_nonpayment": s.DefaultTaxNonpayment,
            "tax_last_date": today,
        },
    )
    logger.info(f"Государство создано: {state_name}")
    return True


async def exists(state_name: str) -> bool:
    return await anyio.Path(_json(state_name)).is_file()


def count() -> int:
    return len(list(pathes.states.glob("*.json")))


async def iter_states() -> AsyncIterator[tuple[str, dict]]:
    async for file in def_dir.glob("*.json"):
        try:
            yield file.stem, await files.load_json_async(file)
        except Exception as e:
            logger.error(f"Не удалось загрузить гос-во {file.name}: {e}")


async def get_all(sort_by: str = "players") -> dict[str, dict]:
    all_data = {name: data async for name, data in iter_states()}
    key = (
        (lambda i: i[1].get("money", 0))
        if sort_by == "money"
        else (lambda i: len(i[1].get("players", [])))
    )
    return dict(sorted(all_data.items(), key=key, reverse=True))


async def if_author(player_id: int) -> str | None:
    async for name, data in iter_states():
        if data.get("author") == player_id:
            return name
    return None


async def if_player(player_id: int) -> str | None:
    async for name, data in iter_states():
        if player_id in data.get("players", []):
            return name
    return None


async def remove(state_name: str) -> bool:
    try:
        state = await State(state_name)
    except FileNotFoundError:
        return False
    return await state.remove()
