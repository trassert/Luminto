import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from random import choice, randint, sample
from time import time
from typing import TypedDict

import aiofiles
import anyio
import asyncmy
import orjson
from loguru import logger

from . import config, formatter, get_theme, pathes

logger.info(f"Загружен модуль {__name__}!")


def _load_json_sync(filepath: Path) -> dict:
    """Загружает JSON файл синхронно."""
    with filepath.open("rb") as f:
        raw = f.read()
    return orjson.loads(raw)


def _save_json_sync(
    filepath: Path,
    data: dict,
    sort_keys: bool = False,
    indent: bool = False,
):
    """Сохраняет JSON файл синхронно."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    options = 0
    if sort_keys:
        options |= orjson.OPT_SORT_KEYS
    if indent:
        options |= orjson.OPT_INDENT_2
    with filepath.open("wb") as f:
        f.write(orjson.dumps(data, option=options))


_file_locks: dict[str, asyncio.Lock] = {}
_locks_lock = asyncio.Lock()


async def get_lock(filepath: Path) -> asyncio.Lock:
    path_str = str(await anyio.Path(filepath).resolve())
    async with _locks_lock:
        if path_str not in _file_locks:
            _file_locks[path_str] = asyncio.Lock()
        return _file_locks[path_str]


async def _load_json_async(filepath: Path) -> dict:
    """Загружает JSON файл асинхронно."""
    lock = await get_lock(filepath)
    async with lock:
        async with aiofiles.open(filepath, "rb") as f:
            raw = await f.read()
    return orjson.loads(raw)


async def _save_json_async(
    filepath: Path,
    data: dict,
    sort_keys: bool = False,
    indent: bool = False,
):
    """Сохраняет JSON файл асинхронно."""
    lock = await get_lock(filepath)
    async with lock:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        options = 0
        if sort_keys:
            options |= orjson.OPT_SORT_KEYS
        if indent:
            options |= orjson.OPT_INDENT_2
        async with aiofiles.open(filepath, "wb") as f:
            return await f.write(orjson.dumps(data, option=options))


async def get_money(id: int) -> int:
    """Получение баланса с защитой от чтения во время записи."""
    id_str = str(id)
    data = await _load_json_async(pathes.money)
    return data.get(id_str, 0)


async def get_all_money():
    """Получить все деньги"""
    data = await _load_json_async(pathes.money)
    return sum(data.values())


async def add_money(id: int, count: int):
    """
    Атомарное изменение баланса.
    """
    id_str = str(id)
    data = await _load_json_async(pathes.money)

    old = data.get(id_str, 0)
    new_val = max(old + count, 0)
    data[id_str] = new_val

    await _save_json_async(pathes.money, data, indent=True)

    logger.info(f"Изменён баланс {id} ({old} -> {new_val})")
    return new_val


async def check_and_update_withdraw_limit(id: int, amount: int) -> tuple[bool, int]:
    """
    Атомарная проверка и обновление day-limit.
    Должна вызываться внутри async with await get_user_lock(id).
    """
    id_str = str(id)
    today = datetime.now().date()

    data = await _load_json_async(pathes.wdraw)

    already_withdrawn = 0
    record_date = None

    if id_str in data:
        try:
            record_date = datetime.strptime(data[id_str]["date"], "%Y-%m-%d").date()
            already_withdrawn = data[id_str].get("withdrawn", 0)
        except KeyError, ValueError:
            record_date = None

    if record_date != today:
        data[id_str] = {"date": today.isoformat(), "withdrawn": amount}
        await _save_json_async(pathes.wdraw, data, indent=True)
        return True, 64 - amount

    remaining = 64 - already_withdrawn
    if amount > remaining:
        return False, remaining

    data[id_str]["withdrawn"] = already_withdrawn + amount
    await _save_json_async(pathes.wdraw, data, indent=True)
    return True, remaining


async def rollback_withdraw_limit(id: int, amount: int):
    """Откатывает лимит назад."""
    id_str = str(id)
    data = await _load_json_async(pathes.wdraw)

    if id_str in data:
        current = data[id_str].get("withdrawn", 0)
        data[id_str]["withdrawn"] = max(0, current - amount)
        await _save_json_async(pathes.wdraw, data, indent=True)


async def update_shop():
    """Обновляет магазин, возвращая новую тему."""
    last_theme = (await _load_json_async(pathes.shopc)).get("theme")
    all_themes = await _load_json_async(pathes.shop)

    if not isinstance(all_themes, dict) or not all_themes:
        logger.exception("Файл shop_all.json пуст или не содержит тем.")
        return None

    theme_names = list(all_themes.keys())
    if last_theme in theme_names and len(theme_names) == 1:
        logger.exception("Нет доступных альтернативных тем в shop_all.json")
        return None

    weights = config.cfg.ShopThemeWeights

    new_theme = last_theme
    attempts = 0
    while new_theme == last_theme and attempts < 10:
        new_theme = get_theme.weighted_choice(theme_names, weights)
        attempts += 1
    if new_theme == last_theme:
        others = [t for t in theme_names if t != last_theme]
        new_theme = choice(others) if others else last_theme

    theme_items = all_themes.get(new_theme, {})
    if not isinstance(theme_items, dict):
        logger.exception(f"Тема '{new_theme}' не содержит предметов")
        return None

    item_names = list(theme_items.keys())
    if len(item_names) < 5:
        logger.exception(
            f"В теме '{new_theme}' недостаточно предметов (минимум 5, найдено {len(item_names)})",
        )
        return None

    selected_items = sample(item_names, 5) if len(item_names) > 5 else item_names[:5]

    current_shop = {"theme": new_theme}
    for item in selected_items:
        item_data = theme_items[item].copy()
        price = item_data.get("price")
        if (
            isinstance(price, list)
            and len(price) == 2
            and all(isinstance(p, int) for p in price)
        ):
            item_data["price"] = randint(price[0], price[1])
        elif not isinstance(price, (int, float)):
            logger.exception(f"Некорректный формат цены для предмета '{item}': {price}")
        current_shop[item] = item_data

    await _save_json_async(pathes.shopc, current_shop, indent=True)
    return new_theme


async def get_shop() -> dict:
    return await _load_json_async(pathes.shopc)


async def shop_version(update=False) -> int:
    async with aiofiles.open(pathes.shopver) as f:
        ver = int(await f.read())
    if update:
        ver += 1
        async with aiofiles.open(pathes.shopver, "w") as f:
            await f.write(str(ver))
    return ver


async def ready_to_mine(id: str) -> bool:
    id = str(id)
    data = await _load_json_async(pathes.mine)
    now = int(time())
    last = data.get(id, 0)
    if now - last > config.cfg.MineWait:
        data[id] = now
        await _save_json_async(pathes.mine, data, indent=True)
        return True
    return False


class Roles:
    BLACKLIST = -1
    USER = 0
    VIP = 1
    INTERN = 2
    MODER = 3
    ADMIN = 4
    OWNER = 5

    async def get(self, id: str) -> int:
        """Получить роль пользователя (USER, если не найдено)"""
        id = str(id)
        data = await _load_json_async(pathes.roles)
        return data.get(id, self.USER)

    async def set(self, id: str, role: int) -> bool:
        """Установить роль пользователя"""
        id = str(id)
        role = int(role)
        data = await _load_json_async(pathes.roles)
        data[id] = role
        sorted_data = dict(sorted(data.items(), key=lambda x: (-x[1], x[0])))
        await _save_json_async(pathes.roles, sorted_data, indent=True)
        return True


class Crorostat:
    def __init__(self, id=False):
        if id:
            self.id = str(id)

    async def get(self):
        data = await _load_json_async(pathes.crocostat)
        if self.id in data:
            return data[self.id]
        data[self.id] = 0
        await _save_json_async(pathes.crocostat, data, sort_keys=True)
        return 0

    async def add(self):
        data = await _load_json_async(pathes.crocostat)
        data[self.id] = data.get(self.id, 0) + 1
        await _save_json_async(pathes.crocostat, data, sort_keys=True)

    async def get_all(self=False):
        data = await _load_json_async(pathes.crocostat)
        return dict(sorted(data.items(), key=lambda item: item[1], reverse=True))


class Nicks:
    def __init__(self, nick=None, id=None):
        self.nick = nick
        self.id = id

    async def get(self, if_nothing=None) -> str | None:
        if self.nick:
            data = await _load_json_async(pathes.nick)
            nick_lower = self.nick.lower()
            for key, value in data.items():
                if key.lower() == nick_lower:
                    return value
            return if_nothing
        if self.id:
            data = await _load_json_async(pathes.nick)
            for key, value in data.items():
                if value == self.id:
                    return key
            return if_nothing
        return if_nothing

    async def get_all(self):
        data = await _load_json_async(pathes.nick)
        return dict(sorted(data.items()))

    async def link(self):
        data = await _load_json_async(pathes.nick)
        keys_to_remove = [k for k, v in data.items() if v == self.id]
        for k in keys_to_remove:
            del data[k]
        data[self.nick] = int(self.id)
        await _save_json_async(pathes.nick, data, indent=True)
        return True


class Statistic:
    def __init__(self, days=1):
        self.days = days

    async def get(self, nick, all_days=False, data=False):
        filepath = pathes.stats / f"{nick}.json"
        if not filepath.exists():
            stats = {datetime.now().strftime("%Y.%m.%d"): 0}
            await _save_json_async(filepath, stats, sort_keys=True)
            return 0

        stats = await _load_json_async(filepath)
        if all_days:
            return sum(stats.values()) or 0

        start_date = datetime.now() - timedelta(days=self.days)
        filtered = {
            date: value
            for date, value in stats.items()
            if datetime.strptime(date, "%Y.%m.%d") >= start_date
        }
        return filtered if data else sum(filtered.values()) or 0

    async def get_all(self, all_days=False):
        data = {}
        for file in pathes.stats.iterdir():
            if file.suffix != ".json":
                continue
            nick = file.stem
            try:
                nick_stat = await self.get(nick, all_days=all_days)
            except Exception:
                logger.warning(f"Ошибка при получении статистики для игрока {nick}")
                continue
            else:
                if nick_stat > 1:
                    data[nick] = nick_stat
        return sorted(data.items(), key=lambda item: item[1], reverse=True)

    async def add(self, date=None):
        now = date or datetime.now().strftime("%Y.%m.%d")
        raw_name = str(self)
        safe_name = Path(raw_name).name
        if safe_name != raw_name or not safe_name:
            logger.warning(f"Некорректное имя статистики: {raw_name!r}")
            return
        filepath = pathes.stats / f"{safe_name}.json"
        base_stats = pathes.stats.resolve()
        resolved_filepath = filepath.resolve()
        try:
            resolved_filepath.relative_to(base_stats)
        except ValueError:
            logger.warning(
                f"Заблокирован выход за пределы каталога статистики: {raw_name!r}"
            )
            return
        try:
            stats = await _load_json_async(resolved_filepath)
        except FileNotFoundError:
            stats = {}
        stats[now] = stats.get(now, 0) + 1
        await _save_json_async(resolved_filepath, stats, sort_keys=True)

    async def get_raw(self) -> dict[str, int]:
        totals = defaultdict(int)
        for json_file in pathes.stats.iterdir():
            if json_file.suffix != ".json":
                continue
            filepath = json_file
            try:
                data = await _load_json_async(filepath)
                for date, count in data.items():
                    totals[date] += count
            except Exception:
                logger.error(f"Ошибка при чтении файла - {json_file.name}")
                continue

        if self.days <= 0:
            return dict(sorted(totals.items(), key=lambda item: item[0]))

        start_date = datetime.now() - timedelta(days=self.days)
        return {
            date: value
            for date, value in totals.items()
            if datetime.strptime(date, "%Y.%m.%d") >= start_date
        }


class Ticket:
    async def get(self):
        self = str(self)
        if not pathes.tickets.exists():
            await _save_json_async(pathes.tickets, {})
            return None
        data = await _load_json_async(pathes.tickets)
        return data.get(self)

    async def add(self, value):
        data = await _load_json_async(pathes.tickets)
        while True:
            random_id = str(randint(1000, 9999))
            if random_id not in data:
                break
        data[random_id] = {"author": int(self), "value": int(value)}
        await _save_json_async(pathes.tickets, data, indent=True)
        return random_id

    async def delete(self):
        data = await _load_json_async(pathes.tickets)
        if self not in data:
            return None
        del data[self]
        await _save_json_async(pathes.tickets, data, indent=True)
        return True


class State:
    def __init__(self, name):
        self.name = name
        self._info()

    def _info(self):
        data = _load_json_sync(pathes.states / f"{self.name}.json")
        self.all = data
        self.price = data["price"]
        self.enter = data["enter"]
        self.desc = data["desc"]
        self.players = data["players"]
        self.type = data["type"]
        self.date = data["date"]
        self.author = data["author"]
        self.coordinates = data["coordinates"]
        self.money = data["money"]
        self.recognition_votes = data.get("recognition_votes", [])
        self.recognition_pending = data.get("recognition_pending", False)

    @property
    def is_recognized(self) -> bool:
        """Государство признано, если выполнено любое из условий."""
        if self.type >= 1:
            return True
        if self.money >= 500:
            return True
        total = States.count()
        if total > 1 and len(self.recognition_votes) / (total - 1) > 0.5:
            return True
        return False

    def change(self, key, value):
        self.all[key] = value
        _save_json_sync(pathes.states / f"{self.name}.json", self.all, indent=True)

    def rename(self, new_name: str):
        new_path = pathes.states / f"{new_name}.json"
        if new_path.exists():
            return False
        (pathes.states / f"{self.name}.json").rename(new_path)
        self.name = new_name
        self._info()
        return None


class States:
    def add(self, author):
        filepath = pathes.states / f"{self}.json"
        if filepath.exists():
            return None
        data = {
            "price": 0,
            "enter": True,
            "desc": "Пусто",
            "players": [],
            "type": 0,
            "date": datetime.now().strftime("%Y.%m.%d"),
            "money": 0,
            "author": author,
            "coordinates": "Не найдено",
        }
        _save_json_sync(filepath, data, indent=True)
        return True

    def check(self):
        return (pathes.states / f"{self}.json").exists()

    def get_all(self="players"):
        all_data = {}
        for file in pathes.states.iterdir():
            if file.suffix != ".json":
                continue
            name = file.stem
            try:
                all_data[name] = _load_json_sync(file)
            except Exception:
                logger.error(f"Не удалось просмотреть гос-во {file.name}")
        if self == "money":

            def key_func(item):
                return item[1]["money"]
        else:

            def key_func(item):
                return len(item[1]["players"])

        return dict(sorted(all_data.items(), key=key_func, reverse=True))

    def if_author(self: int) -> str | bool:
        for file in pathes.states.iterdir():
            if file.suffix != ".json":
                continue
            data = _load_json_sync(file)
            if data["author"] == self:
                return file.stem
        return False

    def if_player(self: int):
        for file in pathes.states.iterdir():
            if file.suffix != ".json":
                continue
            data = _load_json_sync(file)
            if self in data["players"]:
                return file.stem
        return False

    def count() -> int:
        """Количество существующих государств."""
        return sum(1 for f in pathes.states.iterdir() if f.suffix == ".json")

    def find(self: str) -> bool:
        return (pathes.states / f"{self}.json").exists()

    def remove(self: str) -> bool:
        state_path = pathes.states / f"{self}.json"
        if not state_path.exists():
            return False
        pic_path = pathes.states_pic / f"{self}.png"
        if pic_path.exists():
            pic_path.rename(pathes.old_states / f"{self}.png")
        state_path.rename(pathes.old_states / f"{self}.json")
        return True


class Mysql:
    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        db: str,
        table_name: str,
        port: int = 3306,
        minsize: int = 1,
        maxsize: int = 10,
    ):
        self.host = host
        self.user = user
        self.password = password
        self.db = db
        self.port = port
        self.minsize = minsize
        self.maxsize = maxsize
        self.pool = None
        self.table_name = table_name

    async def initialize(self):
        self.pool = await asyncmy.create_pool(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            db=self.db,
            minsize=self.minsize,
            maxsize=self.maxsize,
        )

    async def get_by_id(self, id: int) -> dict[str, int]:
        async with self.pool.acquire() as conn, conn.cursor() as cur:
            await cur.execute(
                f"SELECT wins_casino, lose_moneys_in_casino FROM {self.table_name} WHERE id = %s",
                (id,),
            )
            result = await cur.fetchone()
            if result:
                return {
                    "wins_casino": result[0],
                    "lose_moneys_in_casino": result[1],
                }
            return {"wins_casino": 0, "lose_moneys_in_casino": 0}

    async def get_all(self) -> dict[int, dict[str, int]]:
        async with self.pool.acquire() as conn, conn.cursor() as cur:
            await cur.execute(
                f"SELECT id, wins_casino, lose_moneys_in_casino FROM {self.table_name}",
            )
            results = await cur.fetchall()
            return {
                row[0]: {"wins_casino": row[1], "lose_moneys_in_casino": row[2]}
                for row in results
            }

    async def add_win(self, id: int):
        async with self.pool.acquire() as conn, conn.cursor() as cur:
            await cur.execute(
                f"INSERT INTO {self.table_name} (id, wins_casino, lose_moneys_in_casino) "
                f"VALUES (%s, 1, 0) ON DUPLICATE KEY UPDATE wins_casino = wins_casino + 1",
                (id,),
            )
            await conn.commit()

    async def add_lose_money(self, id: int, amount: int = 1):
        async with self.pool.acquire() as conn, conn.cursor() as cur:
            await cur.execute(
                f"INSERT INTO {self.table_name} (id, wins_casino, lose_moneys_in_casino) "
                f"VALUES (%s, 0, %s) ON DUPLICATE KEY UPDATE lose_moneys_in_casino = lose_moneys_in_casino + %s",
                (id, amount, amount),
            )
            await conn.commit()


Users = Mysql(
    host=config.tokens.mysql_users.host,
    user=config.tokens.mysql_users.user,
    password=config.tokens.mysql_users.password,
    db=config.tokens.mysql_users.database,
    table_name=config.tokens.mysql_users.table,
)


class Notes:
    def __init__(self, storage_dir=pathes.notes):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, name: str) -> Path:
        return self.storage_dir / f"{name}.txt"

    def get(self, name: str):
        file_path = self._get_file_path(name.lower())
        if not file_path.exists():
            return None
        with file_path.open() as f:
            return f.read()

    def create(self, name: str, text: str):
        file_path = self._get_file_path(name.lower())
        if file_path.exists():
            return False
        with file_path.open("w") as f:
            f.write(text)
        return True

    def remove(self, name: str):
        file_path = self._get_file_path(name.lower())
        if not file_path.exists():
            return False
        file_path.unlink()
        return True

    def get_all(self) -> list[str]:
        if not self.storage_dir.exists():
            return []
        return [f.stem for f in self.storage_dir.iterdir() if f.is_file()]


class RefCodes:
    async def _read(self) -> dict:
        return await _load_json_async(pathes.ref)

    async def _write(self, data):
        return await _save_json_async(pathes.ref, data, indent=True)

    async def get_own(self, id: int, default=None) -> str:
        return (await self._read()).get(str(id), {}).get("own", default)

    async def check_uses(self, id: int, default=None) -> list[str]:
        if default is None:
            default = []
        return (await self._read()).get(str(id), {}).get("used", default)

    async def add_own(self, id: int, name: str):
        if await self.check_ref(name) is not None:
            return False
        load = await self._read()
        if str(id) not in load:
            load[str(id)] = {}
        load[str(id)]["own"] = name
        await self._write(load)
        return None

    async def add_uses(self, id: int, who_used: int):
        load = await self._read()
        used_list = load.get(str(id), {}).get("used", [])
        used_list.append(str(who_used))
        load[str(id)]["used"] = used_list
        await self._write(load)

    async def check_ref(self, name) -> str | None:
        load = await self._read()
        for user_id, data in load.items():
            try:
                if data.get("own", "").lower() == name.lower():
                    return user_id
            except Exception:
                pass
        return None

    async def delete(self, id) -> bool:
        "Удаляет реф. код, return bool True/False (есть рефка или нет)"
        load = await self._read()
        try:
            del load[str(id)]["own"]
        except KeyError:
            return False
        await self._write(load)
        return True

    async def get_top_uses(self) -> list[list[str, int]]:
        result = []
        for user_id, info in (await self._read()).items():
            used = info.get("used", None)
            if used:
                result.append([user_id, len(used)])
        return sorted(result, key=lambda x: x[1], reverse=True)


class CitiesGame:
    def __init__(self):
        self.data_file = pathes.cities
        self.data = self._load_data()

    def _load_data(self) -> dict:
        if self.data_file.exists():
            return _load_json_sync(self.data_file)
        return {
            "current_game": {
                "players": [],
                "current_player_id": 0,
                "last_city": None,
                "cities": [],
            },
            "statistics": {},
            "status": False,
            "start_players": 0,
            "id": 0,
        }

    def logger(self, msg: str):
        logger.info(f"[Города] {msg}")

    def _save_data(self):
        _save_json_sync(self.data_file, self.data, indent=True)

    def get_players(self) -> list[int]:
        return self.data["current_game"]["players"]

    def add_player(self, player_id: int):
        if player_id not in self.data["current_game"]["players"]:
            self.data["current_game"]["players"].append(player_id)
            self.data["start_players"] = self.data.get("start_players", 0) + 1
            self._save_data()

    def rem_player(self, player_id: int):
        self.next_answer()
        if player_id in self.data["current_game"]["players"]:
            self.data["current_game"]["players"].remove(player_id)
        if len(self.data["current_game"]["players"]) < 2:
            return False
        self._save_data()
        return self.who_answer()

    def who_answer(self) -> int | None:
        players = self.get_players()
        return self.data["current_game"]["current_player_id"] if players else None

    def next_answer(self):
        players = self.get_players()
        if not players:
            return
        current_id = self.data["current_game"]["current_player_id"]
        if current_id not in players:
            self.data["current_game"]["current_player_id"] = players[0]
            self._save_data()
            return
        idx = players.index(current_id)
        self.data["current_game"]["current_player_id"] = players[
            (idx + 1) % len(players)
        ]
        self.logger(
            f"Очередь игрока {self.data['current_game']['current_player_id']} отвечать",
        )
        self._save_data()

    def get_all_stat(self) -> dict[int, int]:
        return dict(
            sorted(
                self.data["statistics"].items(),
                key=lambda item: item[1],
                reverse=True,
            ),
        )

    def end_game(self):
        self.data["current_game"] = {
            "players": [],
            "current_player_id": 0,
            "last_city": None,
            "cities": [],
        }
        self.data["start_players"] = 0
        self.data["status"] = False
        self.data["statistics"] = {}
        self.data["id"] = (self.data.get("id", 0) + 1) % 10 or 1
        self.logger("Экземпляр Города закончен.")
        self._save_data()

    def start_game(self):
        city = choice((pathes.chk_city).read_text(encoding="utf8").splitlines())
        self.data["id"] = (self.data.get("id", 0) + 1) % 10 or 1
        self.data["status"] = True
        self.data["current_game"]["last_city"] = city
        self.data["current_game"]["current_player_id"] = choice(self.get_players())
        self.logger(f"Запущена игра Города. Начинается с города {city}")
        self.logger(f"Игроки: {self.get_players()}")
        self.logger(f"Отвечает: {self.data['current_game']['current_player_id']}")
        self._save_data()
        return self.data

    def answer(self, id: str, city: str):
        city = city.strip().lower()
        players = self.data["current_game"]["players"]
        if str(id) not in map(str, players):
            self.logger(f"{id} не в списке игроков")
            return 3
        if str(id) != str(self.data["current_game"]["current_player_id"]):
            self.logger(f"{id} сейчас не должен отвечать")
            return 2
        valid_cities = set((pathes.chk_city).read_text(encoding="utf8").splitlines())
        if city not in valid_cities:
            self.logger(f"{id} ответил неизвестным городом")
            return 1
        last_city = self.data["current_game"]["last_city"]
        if city[0] != formatter.city_last_letter(last_city):
            self.logger(
                f"{id} ответил городом с разными буквами ({city[0]} != {last_city[-1]})",
            )
            return 4
        if city in self.data["current_game"]["cities"]:
            self.logger(f"{id} ответил городом, который был")
            return 5
        self.data["current_game"]["last_city"] = city
        self.data["statistics"][str(id)] = self.data["statistics"].get(str(id), 0) + 1
        self.data["current_game"]["cities"].append(city)
        self.next_answer()
        self._save_data()
        return 0

    def get_last_city(self) -> str | None:
        return self.data["current_game"]["last_city"]

    def get_game_status(self):
        return self.data["status"]

    def get_count_players(self):
        return self.data.get("start_players", 0)

    def get_id(self):
        return self.data.get("id", 0)


def hellomsg_check(input_id):
    id_str = str(input_id)
    ids_list = _load_json_sync(pathes.hellomsg)
    if not isinstance(ids_list, list):
        ids_list = []
    if id_str in ids_list:
        return False
    ids_list.append(id_str)
    _save_json_sync(pathes.hellomsg, ids_list, indent=True)
    return True


def mailing_get():
    data = _load_json_sync(pathes.mailing)
    return data if isinstance(data, dict) else {"subscribers": []}


def mailing_save(data):
    _save_json_sync(pathes.mailing, data)


async def get_votes(player: str) -> int:
    player = str(player)
    data = await _load_json_async(pathes.votes)
    return data.get(player, 0)


async def add_votes(player: str, count: int = 1) -> None:
    player = str(player)
    data = await _load_json_async(pathes.votes)
    data[player] = data.get(player, 0) + count
    if data[player] == config.cfg.Advancements.Votes:
        pass
    await _save_json_async(pathes.votes, data)


async def get_crocodile_word() -> str:
    words = await _load_json_async(pathes.crocomap)
    return choice(list(words))


async def add_pending_hint(user_id: int | str, hint_string: str, word: str) -> int:
    data = await _load_json_async(pathes.pending_hints)
    pending_id = max((int(k) for k in data), default=0) + 1
    data[str(pending_id)] = {
        "user": str(user_id),
        "hint": str(hint_string),
        "word": str(word),
    }
    await _save_json_async(pathes.pending_hints, data, indent=True)
    return pending_id


async def remove_pending_hint(id: int | str):
    data = await _load_json_async(pathes.pending_hints)
    if str(id) not in data:
        return None
    del data[str(id)]
    await _save_json_async(pathes.pending_hints, data, indent=True)
    return True


async def get_latest_pending_hint() -> dict:
    data = await _load_json_async(pathes.pending_hints)
    try:
        hint_id = list(data.keys())[-1]
    except IndexError:
        return {}
    hint = data.get(hint_id, {})
    hint["id"] = hint_id
    return hint


async def get_hint_byid(id: str | int) -> dict | None:
    data = await _load_json_async(pathes.pending_hints)
    return data.get(str(id))


async def append_hint(word: str, hint: str):
    data = await _load_json_async(pathes.crocomap)
    word_hints = data.get(word, [])
    if hint not in word_hints:
        word_hints.append(hint)
    data[word] = word_hints
    await _save_json_async(pathes.crocomap, data, indent=True)


async def add_mine_top(id: int | str, count: int):
    id = str(id)
    data = await _load_json_async(pathes.mine_stat)
    data[id] = data.get(id, 0) + int(count)
    await _save_json_async(pathes.mine_stat, data, indent=True)


async def get_mine_top() -> list[list[str, int]]:
    return sorted(
        (await _load_json_async(pathes.mine_stat)).items(),
        key=lambda x: -x[1],
    )


class Item(TypedDict):
    author_id: int
    item: str
    count: int
    price: int


async def add_item(id: str, author_id: int, item: str, count: int, price: int) -> None:
    """Добавляет новый товар по ID. Перезаписывает, если уже существует."""
    data = await _load_json_async(pathes.items)
    data[str(id)] = {
        "author_id": author_id,
        "item": item,
        "count": count,
        "price": price,
    }
    await _save_json_async(pathes.items, data, indent=True)


async def get_item(id: str) -> Item | None:
    """Возвращает товар по ID или None, если не найден."""
    data = await _load_json_async(pathes.items)
    raw_item = data.get(str(id))
    if raw_item is None:
        return None
    return raw_item


async def remove_item(id: str) -> bool:
    """Удаляет товар по ID. Возвращает True, если существовал и удалён."""
    data = await _load_json_async(pathes.items)
    id = str(id)
    if id not in data:
        return False
    del data[id]
    await _save_json_async(pathes.items, data, indent=True)
    return True


class CrocodileGame:
    def __init__(self):
        self.data_file = pathes.crocodile
        self.data = self._load_data()

    def _load_data(self):
        try:
            return _load_json_sync(self.data_file)
        except FileNotFoundError:
            return {"bets": {}, "current_game": {}}

    async def _save_data(self, data):
        await _save_json_async(self.data_file, data)

    async def add_bet(self, user_id: int, bet: int):
        """Добавляет (или уменьшает) ставку пользователя. Возвращает True/False."""
        bets = self.data.setdefault("bets", {})
        cur = bets.get(str(user_id), 0) + bet
        if cur < 0:
            return False
        bets[str(user_id)] = cur
        self.data["bets"] = bets
        await self._save_data(self.data)
        return True

    def get_current(self):
        """Возвращает текущее состояние игры или 0, если игры нет."""
        return self.data.get("current_game", 0)

    async def set_current(self, value):
        """Устанавливает текущее состояние игры и сохраняет файл."""
        self.data["current_game"] = value
        await self._save_data(self.data)

    async def is_running(self) -> bool:
        return self.get_current() != 0

    async def start_game(self, word: str):
        """Запускает игру с указанным словом."""
        payload = {
            "hints": [],
            "word": str(word),
            "unsec": "".join("_" if x.isalpha() else x for x in str(word)),
        }
        await self.set_current(payload)
        return payload

    async def stop_game(self):
        """Останавливает текущую игру, возвращая слово и очищая состояние."""
        current = self.get_current()
        word = None
        if isinstance(current, dict):
            word = current.get("word")
        await self.set_current(0)

        await self.clear_bets()
        return word

    def get_bets(self) -> dict:
        return dict(self.data.get("bets", {}))

    async def set_bets(self, bets: dict):
        self.data["bets"] = dict(bets)
        await self._save_data(self.data)

    async def clear_bets(self):
        self.data["bets"] = {}
        await self._save_data(self.data)

    async def add_hint(self, user_id: int) -> bool:
        """Добавляет пользователя в список запросивших подсказку. Возвращает False если уже просил."""
        current = self.get_current()
        if not current or not isinstance(current, dict):
            return False
        hints = current.get("hints", [])
        if user_id in hints:
            return False
        hints.append(user_id)
        current["hints"] = hints
        await self.set_current(current)
        return True

    async def reveal_on_guess(self, guess: str):
        """Обновляет маску (`unsec`) по частичному отгадыванию.
        Возвращает tuple (changed: bool, new_mask: str, finished_full_mask: bool).
        finished_full_mask=True означает, что маска совпала с словом (до исправления).
        """
        current = self.get_current()
        if not current or not isinstance(current, dict):
            return False, None, False
        word = current.get("word", "")
        mask = list(current.get("unsec", ""))
        changed = False
        for i, ch in enumerate(word):
            if i < len(guess) and guess[i] == ch and mask[i] == "_":
                mask[i] = ch
                changed = True

        new_mask_str = "".join(mask)
        finished = False
        if new_mask_str == word:
            if len(mask) > 0:
                mask[randint(0, len(mask) - 1)] = "_"
            new_mask_str = "".join(mask)
            finished = True

        current["unsec"] = new_mask_str
        await self.set_current(current)
        return changed, new_mask_str, finished

    async def guess_word(self, user_id: int, guess: str):
        """Пытается угадать слово полностью. Возвращает словарь с результатом.
        {"win": bool, "word": str, "bets": dict}
        """
        current = self.get_current()
        if not current or not isinstance(current, dict):
            return {"win": False}
        word = current.get("word")
        if str(guess).strip().lower() == str(word).strip().lower():
            bets = self.get_bets()

            await self.set_current(0)
            await self.clear_bets()
            return {"win": True, "word": word, "bets": bets}
        return {"win": False}

    def get_last_hint(self):
        """Возвращает значение последней подсказки (обычно int) или 0."""
        return self.data.get("crocodile_last_hint", 0)

    async def set_last_hint(self, value):
        self.data["crocodile_last_hint"] = value
        await self._save_data(self.data)

    async def clear_last_hint(self):
        if "crocodile_last_hint" in self.data:
            del self.data["crocodile_last_hint"]
            await self._save_data(self.data)


class Topics:
    def __init__(self):
        self.data_file = pathes.topics
        if not self.data_file.exists():
            _save_json_sync(self.data_file, {})

    def idconv(self, id):
        try:
            return str(id)
        except Exception:
            msg = f"Невозможно конвертировать ID {id} в строку"
            raise ValueError(msg)

    async def get_byid(self, id: str) -> dict:
        id = self.idconv(id)
        self.data = await _load_json_async(self.data_file)
        return self.data.get(id, [])

    async def add(self, id: str, topic_id: str) -> None:
        id = self.idconv(id)
        topic_id = str(topic_id)
        self.data = await _load_json_async(self.data_file)
        self.data[id] = self.data.get(id, []).append(topic_id)
        return await _save_json_async(self.data_file, self.data, indent=True)

    async def remove(self, id: str, topic_id: str) -> bool:
        id = self.idconv(id)
        topic_id = str(topic_id)
        self.data = await _load_json_async(self.data_file)
        if topic_id in self.data.get(id, []):
            self.data[id].remove(topic_id)
            await _save_json_async(self.data_file, self.data, indent=True)
            return True
        return False
