import atexit
import time
from typing import Any

import aiohttp
import orjson
from loguru import logger

from . import config, files, nicks, pathes

logger.info(f"Загружен модуль {__name__}!")

DEFAULT = 0
VIP = 1
INTERN = 2
MODER = 3
ADMIN = 4
OWNER = 5
roles = {
    DEFAULT: "default",
    VIP: "вип",
    INTERN: "млмодер",
    MODER: "модер",
    ADMIN: "админ",
    OWNER: "создатель",
}


class LuckPermsRestAPI:
    def __init__(
        self, base_url: str, api_key: str | None = None, timeout: int = 10
    ):
        """
        Инициализация API для взаимодействия с LuckPerms.
        base_url — URL LuckPerms API.
        api_key — API ключ для аутентификации (опционально).
        timeout — таймаут для HTTP-запросов (10 секунд по умолчанию).

        Сессия живёт постоянно, пересоздаётся только если её закрывают (.close())
        """
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        atexit.register(self._cleanup)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._headers, timeout=self._timeout
            )
        return self._session

    async def close(self):
        """
        Закрывает текущую сессию, если она открыта.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _cleanup(self):
        """
        Выполняет синхронную best-effort зачистку на выходе из программы —
        закрывает сессию и освобождает ресурсы.
        """
        if self._session and not self._session.closed:
            connector = self._session.connector
            self._session._connector = None
            if connector is not None and not connector.closed:
                connector._close()
            self._session = None

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        session = await self._get_session()
        async with session.request(
            method, f"{self.base_url}{path}", **kwargs
        ) as resp:
            if resp.status == 404 and "username" in kwargs.get("params", {}):
                msg = f"User '{kwargs['params']['username']}' not found"
                raise ValueError(msg)
            resp.raise_for_status()
            return orjson.loads(await resp.read())

    async def _uuid(self, nick: str) -> str:
        data = await self._request(
            "GET", "/user/lookup", params={"username": nick}
        )
        return data["uniqueId"]

    async def add_role(self, nick: str, role: str) -> list[str]:
        uuid = await self._uuid(nick)
        return await self._request(
            "POST", f"/user/{uuid}/addgroup", data=orjson.dumps({"group": role})
        )

    async def get_roles(self, nick: str) -> list[str]:
        uuid = await self._uuid(nick)
        return await self._request("GET", f"/user/{uuid}/getgroup")

    async def add_temp_role(
        self, nick: str, role: str, seconds: int
    ) -> list[dict]:
        uuid = await self._uuid(nick)
        node = {
            "key": f"group.{role}",
            "value": True,
            "expiry": int(time.time()) + seconds,
        }
        return await self._request(
            "POST", f"/user/{uuid}/nodes", data=orjson.dumps(node)
        )

    async def del_role(self, nick: str, role: str) -> list[str]:
        uuid = await self._uuid(nick)
        return await self._request(
            "DELETE",
            f"/user/{uuid}/delgroup",
            data=orjson.dumps({"group": role}),
        )

    async def get_all_roles(self) -> list[str]:
        return await self._request("GET", "/group")


api = LuckPermsRestAPI(config.cfg.LuckPermsURL)


async def get_role(nick: str) -> int:
    try:
        user_roles = await api.get_roles(nick)
    except ValueError:
        return DEFAULT
    return max(
        (level for level, group in roles.items() if group in user_roles),
        default=DEFAULT,
    )


async def get_user_role(user_id: int) -> int:
    nick = await nicks.get_byid(user_id)
    return await get_role(nick) if nick else DEFAULT


async def set_role(nick: str, role: int) -> None:
    current = await get_role(nick)
    if current == role:
        return
    if current != DEFAULT:
        await api.del_role(nick, roles[current])
    if role != DEFAULT:
        await api.add_role(nick, roles[role])


async def get_blacklist(id: int) -> str | None:
    try:
        data = await files.load_json_async(pathes.blacklist)
    except FileNotFoundError:
        return None
    return data.get(str(id))


async def add_to_blacklist(id: int, reason: str) -> None:
    try:
        data = await files.load_json_async(pathes.blacklist)
    except FileNotFoundError:
        data = {}
    data[str(id)] = reason
    await files.save_json_async(pathes.blacklist, data, indent=True)


async def remove_from_blacklist(id: int) -> bool:
    try:
        data = await files.load_json_async(pathes.blacklist)
    except FileNotFoundError:
        return False
    if str(id) not in data:
        return False
    del data[str(id)]
    await files.save_json_async(pathes.blacklist, data, indent=True)
    return True
