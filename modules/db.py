import asyncio
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from random import choice, randint
from time import time
from typing import TypedDict

import asyncmy
import orjson
from loguru import logger

from . import config, files, formatter, nicks, pathes

logger.info(f"Загружен модуль {__name__}!")


async def get_money(id: int) -> int:
    """Получение баланса с защитой от чтения во время записи."""
    id_str = str(id)
    data = await files.load_json_async(pathes.money)
    return data.get(id_str, 0)


async def get_all_money():
    """Получить все деньги"""
    data = await files.load_json_async(pathes.money)
    return sum(data.values())


async def add_money(id: int, count: int):
    """
    Атомарное изменение баланса.
    """
    id_str = str(id)
    data = await files.load_json_async(pathes.money)
    old = data.get(id_str, 0)
    new_val = max(old + count, 0)
    data[id_str] = new_val
    await files.save_json_async(pathes.money, data, indent=True)
    logger.info(f"Изменён баланс {id} ({old} -> {new_val})")
    return new_val


async def check_and_update_withdraw_limit(
    id: int, amount: int
) -> tuple[bool, int]:
    """
    Атомарная проверка и обновление day-limit.
    """
    id_str = str(id)
    today = datetime.now().date()
    data = await files.load_json_async(pathes.wdraw)
    already_withdrawn = 0
    record_date = None
    if id_str in data:
        try:
            record_date = datetime.strptime(
                data[id_str]["date"], "%Y-%m-%d"
            ).date()
            already_withdrawn = data[id_str].get("withdrawn", 0)
        except KeyError, ValueError:
            record_date = None
    if record_date != today:
        data[id_str] = {"date": today.isoformat(), "withdrawn": amount}
        await files.save_json_async(pathes.wdraw, data, indent=True)
        return True, 64 - amount
    remaining = 64 - already_withdrawn
    if amount > remaining:
        return False, remaining
    data[id_str]["withdrawn"] = already_withdrawn + amount
    await files.save_json_async(pathes.wdraw, data, indent=True)
    return True, remaining


async def rollback_withdraw_limit(id: int, amount: int):
    """Откатывает лимит назад."""
    id_str = str(id)
    data = await files.load_json_async(pathes.wdraw)
    if id_str in data:
        current = data[id_str].get("withdrawn", 0)
        data[id_str]["withdrawn"] = max(0, current - amount)
        await files.save_json_async(pathes.wdraw, data, indent=True)


async def ready_to_mine(id: str) -> bool:
    id = str(id)
    data = await files.load_json_async(pathes.mine)
    now = int(time())
    last = data.get(id, 0)
    if now - last > config.cfg.MineWait:
        data[id] = now
        await files.save_json_async(pathes.mine, data, indent=True)
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
        data = await files.load_json_async(pathes.roles)
        return data.get(id, self.USER)

    async def set(self, id: str, role: int) -> bool:
        """Установить роль пользователя"""
        id = str(id)
        role = int(role)
        data = await files.load_json_async(pathes.roles)
        data[id] = role
        sorted_data = dict(sorted(data.items(), key=lambda x: (-x[1], x[0])))
        await files.save_json_async(pathes.roles, sorted_data, indent=True)
        return True


class Statistic:
    def __init__(self, days=1, nick=None):
        self.days = days
        self.nick = nick

    async def get(self, nick, all_days=False, data=False):
        filepath = pathes.stats / f"{nick}.json"
        if not filepath.exists():
            stats = {datetime.now().strftime("%Y.%m.%d"): 0}
            await files.save_json_async(filepath, stats, sort_keys=True)
            return 0
        stats = await files.load_json_async(filepath)
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
                logger.warning(
                    f"Ошибка при получении статистики для игрока {nick}"
                )
                continue
            else:
                if nick_stat > 1:
                    data[nick] = nick_stat
        return sorted(data.items(), key=lambda item: item[1], reverse=True)

    async def add(self, nick: str = None, date=None):
        """
        Добавляет единицу статистики для игрока.
        Args:
            nick: Имя игрока. Если не указан, используется self.nick
            date: Дата в формате YYYY.MM.DD (опционально)
        """
        target_nick = nick or self.nick
        if not target_nick:
            msg = "Nickname must be provided either as argument or via __init__"
            raise ValueError(msg)
        if not formatter.is_valid_mc_nick(target_nick):
            msg = f"Invalid nickname: {target_nick}"
            raise ValueError(msg)
        now = date or datetime.now().strftime("%Y.%m.%d")
        filepath = pathes.stats / f"{target_nick}.json"
        base_stats = pathes.stats.resolve()
        resolved_filepath = filepath.resolve()
        try:
            resolved_filepath.relative_to(base_stats)
        except ValueError:
            logger.warning(
                f"Заблокирован выход за пределы каталога статистики: {target_nick!r}"
            )
            return
        try:
            stats = await files.load_json_async(resolved_filepath)
        except FileNotFoundError:
            stats = {}
        stats[now] = stats.get(now, 0) + 1
        await files.save_json_async(resolved_filepath, stats, sort_keys=True)

    async def get_raw(self) -> dict[str, int]:
        totals = defaultdict(int)
        for json_file in pathes.stats.iterdir():
            if json_file.suffix != ".json":
                continue
            filepath = json_file
            try:
                data = await files.load_json_async(filepath)
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


class State:
    def __init__(self, name: str):
        self.name = name
        self._load()
        self._lock = asyncio.Lock()

    def _load(self) -> None:
        """Загружает данные из JSON файла."""
        file_path = pathes.states / f"{self.name}.json"

        if not file_path.exists():
            msg = f"State file not found: {file_path}"
            raise FileNotFoundError(msg)

        with file_path.open("rb") as f:
            data = orjson.loads(f.read())

        self._data = data

        self.price = data.get("price")
        self.enter = data.get("enter")
        self.desc = data.get("desc")
        self.players = list(data.get("players", []))  # Всегда список
        self.type = data.get("type")
        self.date = data.get("date")
        self.author = data.get("author")
        self.coordinates = data.get("coordinates")
        self.money = data.get("money")
        self.tax = data.get("tax", config.cfg.States.DefaultTax)
        self.tax_period = data.get(
            "tax_period", config.cfg.States.DefaultTaxPeriod
        )
        self.tax_nonpayment = data.get(
            "tax_nonpayment", config.cfg.States.DefaultTaxNonpayment
        )
        self.tax_last_date = data.get(
            "tax_last_date", datetime.now().strftime("%Y.%m.%d")
        )
        self.recognition_votes = data.get("recognition_votes", [])
        self.recognition_pending = data.get(
            "recognition_pending", config.cfg.States.RecognitionPending
        )

    def _save(self) -> None:
        """Сохраняет текущие данные в JSON файл."""
        file_path = pathes.states / f"{self.name}.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        self._sync_data()

        with file_path.open("wb") as f:
            f.write(
                orjson.dumps(
                    self._data,
                    option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
                )
            )

    def _sync_data(self) -> None:
        """Синхронизирует атрибуты с _data перед сохранением."""
        self._data.update(
            {
                "price": self.price,
                "enter": self.enter,
                "desc": self.desc,
                "players": list(self.players),  # Всегда список
                "type": self.type,
                "date": self.date,
                "author": self.author,
                "coordinates": self.coordinates,
                "money": self.money,
                "tax": self.tax,
                "tax_period": self.tax_period,
                "tax_nonpayment": self.tax_nonpayment,
                "tax_last_date": self.tax_last_date,
                "recognition_votes": self.recognition_votes,
                "recognition_pending": self.recognition_pending,
            }
        )

    @property
    def all(self) -> dict:
        """Возвращает копию всех данных (для обратной совместимости)."""
        self._sync_data()
        return deepcopy(self._data)

    @all.setter
    def all(self, value: dict):
        """Устанавливает все данные (для обратной совместимости)."""
        self._data = deepcopy(value)
        self._load()

    @property
    def is_recognized(self) -> bool:
        """Государство признано, если выполнено любое из условий."""
        if self.type >= 1:
            return True
        if self.money >= 500:
            return True

        total = self._count_states()
        if total > 1 and len(self.recognition_votes) / (total - 1) > 0.5:
            return True

        return False

    @staticmethod
    def _count_states() -> int:
        """Возвращает количество существующих государств."""
        return len(list(pathes.states.glob("*.json")))

    def change(self, key: str, value) -> None:
        """
        Изменяет значение ключа и сохраняет в файл.

        Args:
            key: Имя ключа
            value: Новое значение
        """
        self._data[key] = value
        if hasattr(self, key):
            if key == "players" and not isinstance(value, list):
                value = list(value)
            setattr(self, key, value)
        self._save()

    def rename(self, new_name: str) -> None | bool:
        """
        Переименовывает государство.

        Returns:
            None при успехе, False если файл уже существует
        """
        old_path = pathes.states / f"{self.name}.json"
        new_path = pathes.states / f"{new_name}.json"

        if new_path.exists():
            return False
        old_path.rename(new_path)
        self.name = new_name
        self._load()

        return None

    async def pay_tax(self) -> dict:
        """
        Проверяет и списывает налоги с игроков.

        Returns:
            Dict с информацией о результатах
        """
        async with self._lock:
            try:
                tax_amount = int(self.tax or 0)
            except Exception:
                tax_amount = 0

            if tax_amount <= 0:
                return {"kicked": [], "payed": [], "collected": 0}

            today = datetime.now()
            today_str = today.strftime("%Y.%m.%d")

            payed_players: list = []
            nonpayed_players: list = []
            collected = 0
            players_copy = list(self.players)

            for player_id in players_copy:
                try:
                    balance = await get_money(player_id)
                    balance = int(balance or 0)
                except Exception:
                    balance = 0

                if balance < tax_amount:
                    nonpayed_players.append(player_id)
                else:
                    await add_money(player_id, -tax_amount)
                    payed_players.append(player_id)
                    collected += tax_amount

            if collected:
                new_money = int(self.money or 0) + collected
                self.money = new_money
                self._data["money"] = new_money

            self.tax_last_date = today_str
            self._data["tax_last_date"] = today_str

            kicked: list = []
            if nonpayed_players and self.tax_nonpayment == "kick":
                nonpayed_set = set(nonpayed_players)
                kicked = [p for p in self.players if p in nonpayed_set]
                new_players = [p for p in self.players if p not in nonpayed_set]

                self.players = new_players
                self._data["players"] = new_players

                for player_id in kicked:
                    player_name = await nicks.get_byid(player_id) or str(
                        player_id
                    )
                    logger.info(
                        f"{player_name} ({player_id}) кикнут из {self.name} "
                        f"за неуплату налогов."
                    )

            self._save()

            return {
                "kicked": kicked,
                "payed": payed_players,
                "collected": collected,
            }

    def reload(self) -> None:
        """Перезагружает данные из файла (полезно при внешних изменениях)."""
        self._load()

    def to_dict(self) -> dict:
        """Возвращает копию всех данных в виде словаря."""
        self._sync_data()
        return deepcopy(self._data)

    def __repr__(self) -> str:
        return f"<State(name='{self.name}', players={len(self.players)})>"

    def __str__(self) -> str:
        return self.name


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


class CitiesGame:
    def __init__(self):
        self.data_file = pathes.cities
        self.data = self._load_data()
        self._valid_cities = set(
            pathes.chk_city.read_text(encoding="utf8").splitlines()
        )
        self._cities_list = list(self._valid_cities)

    def _load_data(self) -> dict:
        if self.data_file.exists():
            return files.load_json_sync(self.data_file)
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
        files.save_json_sync(self.data_file, self.data, indent=True)

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
        return (
            self.data["current_game"]["current_player_id"] if players else None
        )

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
        self.data["current_game"]["current_player_id"] = choice(
            self.get_players()
        )
        self.logger(f"Запущена игра Города. Начинается с города {city}")
        self.logger(f"Игроки: {self.get_players()}")
        self.logger(
            f"Отвечает: {self.data['current_game']['current_player_id']}"
        )
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
        if city not in self._valid_cities:
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
        self.data["statistics"][str(id)] = (
            self.data["statistics"].get(str(id), 0) + 1
        )
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
    ids_list = files.load_json_sync(pathes.hellomsg)
    if not isinstance(ids_list, list):
        ids_list = []
    if id_str in ids_list:
        return False
    ids_list.append(id_str)
    files.save_json_sync(pathes.hellomsg, ids_list, indent=True)
    return True


async def mailing_get():
    users = (await nicks.get_all()).values()
    data = await files.load_json_async(pathes.mailing)
    unsub_set = set(data["unsub"])
    return [x for x in users if x not in unsub_set]


async def mailing_addsub(id: int) -> bool:
    if not isinstance(id, int):
        msg = f"Int expected, got {type(id).__name__}"
        raise TypeError(msg)
    data = await files.load_json_async(pathes.mailing)
    if id not in data["unsub"]:
        return False
    data["unsub"].remove(id)
    await files.save_json_async(pathes.mailing, data)
    return True


async def mailing_rmsub(id: int) -> bool:
    if not isinstance(id, int):
        msg = f"Int expected, got {type(id).__name__}"
        raise TypeError(msg)
    data = await files.load_json_async(pathes.mailing)
    if id in data["unsub"]:
        return False
    data["unsub"].append(id)
    await files.save_json_async(pathes.mailing, data)
    return True


async def get_votes(player: str) -> int:
    player = str(player)
    data = await files.load_json_async(pathes.votes)
    return data.get(player, 0)


async def add_votes(player: str, count: int = 1) -> None:
    player = str(player)
    data = await files.load_json_async(pathes.votes)
    data[player] = data.get(player, 0) + count
    if data[player] == config.cfg.Advancements.Votes:
        pass
    await files.save_json_async(pathes.votes, data)


async def get_crocodile_word() -> str:
    words = await files.load_json_async(pathes.crocomap)
    return choice(list(words))


async def add_pending_hint(
    user_id: int | str, hint_string: str, word: str
) -> int:
    data = await files.load_json_async(pathes.pending_hints)
    pending_id = max((int(k) for k in data), default=0) + 1
    data[str(pending_id)] = {
        "user": str(user_id),
        "hint": str(hint_string),
        "word": str(word),
    }
    await files.save_json_async(pathes.pending_hints, data, indent=True)
    return pending_id


async def remove_pending_hint(id: int | str):
    data = await files.load_json_async(pathes.pending_hints)
    if str(id) not in data:
        return None
    del data[str(id)]
    await files.save_json_async(pathes.pending_hints, data, indent=True)
    return True


async def get_latest_pending_hint() -> dict:
    data = await files.load_json_async(pathes.pending_hints)
    try:
        hint_id = list(data.keys())[-1]
    except IndexError:
        return {}
    hint = data.get(hint_id, {})
    hint["id"] = hint_id
    return hint


async def get_hint_byid(id: str | int) -> dict | None:
    data = await files.load_json_async(pathes.pending_hints)
    return data.get(str(id))


async def append_hint(word: str, hint: str):
    data = await files.load_json_async(pathes.crocomap)
    word_hints = data.get(word, [])
    if hint not in word_hints:
        word_hints.append(hint)
    data[word] = word_hints
    await files.save_json_async(pathes.crocomap, data, indent=True)


async def add_mine_top(id: int | str, count: int):
    id = str(id)
    data = await files.load_json_async(pathes.mine_stat)
    data[id] = data.get(id, 0) + int(count)
    await files.save_json_async(pathes.mine_stat, data, indent=True)


async def get_mine_top() -> list[list[str, int]]:
    return sorted(
        (await files.load_json_async(pathes.mine_stat)).items(),
        key=lambda x: -x[1],
    )


class Item(TypedDict):
    author_id: int
    item: str
    count: int
    price: int


async def add_item(
    id: str, author_id: int, item: str, count: int, price: int
) -> None:
    """Добавляет новый товар по ID. Перезаписывает, если уже существует."""
    data = await files.load_json_async(pathes.items)
    data[str(id)] = {
        "author_id": author_id,
        "item": item,
        "count": count,
        "price": price,
    }
    await files.save_json_async(pathes.items, data, indent=True)


async def get_item(id: str) -> Item | None:
    """Возвращает товар по ID или None, если не найден."""
    data = await files.load_json_async(pathes.items)
    raw_item = data.get(str(id))
    if raw_item is None:
        return None
    return raw_item


async def remove_item(id: str) -> bool:
    """Удаляет товар по ID. Возвращает True, если существовал и удалён."""
    data = await files.load_json_async(pathes.items)
    id = str(id)
    if id not in data:
        return False
    del data[id]
    await files.save_json_async(pathes.items, data, indent=True)
    return True


class CrocodileGame:
    def __init__(self):
        self.data_file = pathes.crocodile
        self.data = self._load_data()

    def _load_data(self):
        try:
            return files.load_json_sync(self.data_file)
        except FileNotFoundError:
            return {"bets": {}, "current_game": {}}

    async def _save_data(self, data):
        await files.save_json_async(self.data_file, data)

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
        for i, (w_char, g_char) in enumerate(zip(word, guess)):
            if w_char == g_char and mask[i] == "_":
                mask[i] = w_char
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
            files.save_json_sync(self.data_file, {})

    def idconv(self, id):
        try:
            return str(id)
        except Exception:
            msg = f"Невозможно конвертировать ID {id} в строку"
            raise ValueError(msg)

    async def get_byid(self, id: str) -> dict:
        id = self.idconv(id)
        self.data = await files.load_json_async(self.data_file)
        return self.data.get(id, [])

    async def add(self, id: str, topic_id: str) -> None:
        id = self.idconv(id)
        topic_id = self.idconv(topic_id)
        self.data = await files.load_json_async(self.data_file)
        if id not in self.data:
            self.data[id] = []
        self.data[id].append(topic_id)
        return await files.save_json_async(
            self.data_file, self.data, indent=True
        )

    async def remove(self, id: str, topic_id: str) -> bool:
        id = self.idconv(id)
        topic_id = self.idconv(topic_id)
        self.data = await files.load_json_async(self.data_file)
        if topic_id in self.data.get(id, []):
            self.data[id].remove(topic_id)
            await files.save_json_async(self.data_file, self.data, indent=True)
            return True
        return False
