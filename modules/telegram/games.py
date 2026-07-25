import asyncio
import contextlib
from random import choice, random
from typing import TYPE_CHECKING

import aiofiles
import orjson
from loguru import logger
from telethon import events
from telethon.tl.types import (
    KeyboardButtonCallback,
)

from .. import config, crocostat, db, formatter, pathes, phrase
from . import func
from .client import client

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")

Cities = db.CitiesGame()
CitiesTimerTask: asyncio.Task | None = None
CrocodileGame = db.CrocodileGame()


def _check_topic(event: Message) -> bool:
    """Проверяет, находится ли сообщение в игровом топике."""
    return not (
        event.reply_to_msg_id != config.chats.topics.games
        and getattr(event.reply_to, "reply_to_top_id", None)
        != config.chats.topics.games
    )


async def _safe_delete(message: Message | None):
    """Безопасное удаление сообщения без вылета по ошибке."""
    if message:
        with contextlib.suppress(Exception):
            await message.delete()


@func.new_command("/казино$", chats=config.chats.chat)
@func.new_command("/casino", chats=config.chats.chat)
async def casino(event: Message):
    if not _check_topic(event):
        return await event.reply(phrase.game_topic_warning)

    keyboard = [
        [
            KeyboardButtonCallback(
                text="🎰 Автоматическая прокрутка",
                data=b"casino.auto",
            ),
        ],
    ]
    return await event.reply(
        phrase.casino.start.format(config.cfg.PriceForCasino),
        buttons=keyboard,
    )


@func.new_command(r"/крокодил$")
@func.new_command(r"/crocodile$")
@func.new_command(r"старт крокодил$")
async def crocodile(event: Message):
    if event.chat_id != config.chats.chat:
        return await event.reply(phrase.crocodile.chat)
    if not _check_topic(event):
        return await event.reply(phrase.game_topic_warning)

    is_running = await CrocodileGame.is_running()
    stop_btn = KeyboardButtonCallback(
        text="❌ Остановить игру", data=b"crocodile.stop"
    )

    if not is_running:
        keyboard = [
            [
                KeyboardButtonCallback(
                    text="✅ Играть", data=b"crocodile.start"
                ),
                stop_btn,
            ],
        ]
        return await event.reply(phrase.crocodile.game, buttons=keyboard)

    return await event.reply(phrase.crocodile.no, buttons=[[stop_btn]])


@func.new_command(r"/ставка(.*)")
@func.new_command(r"/крокоставка(.*)")
async def crocodile_bet(event: Message):
    if not _check_topic(event):
        return await event.reply(phrase.game_topic_warning)

    raw_bet = event.pattern_match.group(1).strip()
    min_bet = config.cfg.Crocodile.MinBet
    max_bet = config.cfg.Crocodile.MaxBet

    try:
        bet = int(raw_bet) if raw_bet else min_bet
    except ValueError:
        return await event.reply(phrase.money.nan_count)

    if bet < min_bet:
        return await event.reply(
            phrase.money.min_count.format(
                formatter.value_to_str(min_bet, phrase.currency),
            ),
        )
    if bet > max_bet:
        return await event.reply(
            phrase.money.max_count.format(
                formatter.value_to_str(max_bet, phrase.currency),
            ),
        )

    if await CrocodileGame.is_running():
        return await event.reply(phrase.crocodile.no)

    sender_balance = await db.get_money(event.sender_id)
    if sender_balance < bet:
        return await event.reply(
            phrase.money.not_enough.format(
                formatter.value_to_str(sender_balance, phrase.currency),
            ),
        )

    all_bets = CrocodileGame.get_bets()
    if str(event.sender_id) in all_bets:
        return await event.reply(phrase.crocodile.bet_already)

    await db.add_money(event.sender_id, -bet)
    all_bets[str(event.sender_id)] = bet
    await CrocodileGame.set_bets(all_bets)

    return await event.reply(
        phrase.crocodile.bet.format(
            formatter.value_to_str(bet, phrase.currency)
        ),
    )


async def crocodile_handler(event: Message):
    if not _check_topic(event) or not event.text:
        return None

    text = event.text.strip().lower()
    game_data = CrocodileGame.get_current()
    if not game_data:
        return None

    current_word = game_data["word"]

    if text == current_word:
        bets = CrocodileGame.get_bets()
        total_payout = 0

        top_players = list((await crocostat.get_all()).keys())[
            : config.cfg.TopLowerBets
        ]

        for uid, bet_val in bets.items():
            if str(event.sender_id) == uid:
                multiplier = (
                    config.cfg.TopBets
                    if uid in top_players
                    else config.cfg.CrocodileBetCoo
                )
                total_payout += round(bet_val * multiplier)
            else:
                total_payout += bet_val

        if total_payout > 0:
            await db.add_money(event.sender_id, total_payout)
            win_msg = phrase.crocodile.bet_win.format(
                formatter.value_to_str(total_payout, phrase.currency),
            )
        else:
            win_msg = ""

        await CrocodileGame.stop_game()
        await CrocodileGame.set_last_hint(0)
        client.remove_event_handler(crocodile_hint)
        client.remove_event_handler(crocodile_handler)
        await crocostat.add(event.sender_id)

        return await event.reply(
            phrase.crocodile.win.format(current_word) + win_msg
        )

    if not text.startswith("/"):
        changed, new_mask_str, finished = await CrocodileGame.reveal_on_guess(
            text
        )
        if changed:
            return await event.reply(
                phrase.crocodile.new.format(new_mask_str.replace("_", "..")),
            )
    return None


async def crocodile_hint(event: Message):
    if not _check_topic(event):
        return await event.reply(phrase.game_topic_warning)

    game = CrocodileGame.get_current()
    if not game:
        return None
    added = await CrocodileGame.add_hint(event.sender_id)
    if not added:
        return await event.reply(phrase.crocodile.hints_all)

    game = CrocodileGame.get_current()

    word = game["word"]
    hints_list = game.get("hints", [])

    if random() < config.cfg.PercentForRandomLetter and len(hints_list) > 1:
        for i, letter in enumerate(game["unsec"], 1):
            if letter == "_":
                return await event.reply(
                    f"{i} буква в слове - **{word[i - 1]}**"
                )

    try:
        async with aiofiles.open(pathes.crocomap, "rb") as f:
            mapping = orjson.loads(await f.read())
            if word in mapping:
                return await event.reply(choice(mapping[word]))
    except Exception as e:
        logger.error(f"Ошибка чтения карты подсказок: {e}")


@logger.catch
async def cities_timeout(current_player: int, last_city: str):
    try:
        player_name = await func.get_name(current_player)
        timer_msg: Message | None = None

        for second in range(config.cfg.CitiesTimeout, 0, -1):
            if (
                not Cities.get_game_status()
                or Cities.who_answer() != current_player
                or Cities.get_last_city() != last_city
            ):
                await _safe_delete(timer_msg)
                return None

            if second <= 1:
                await _safe_delete(timer_msg)
                Cities.logger(f"Тайм-аут игрока {current_player}")

                players = Cities.get_players()
                players_count = Cities.get_count_players()
                next_player = Cities.rem_player(current_player)

                if next_player is False:
                    winner_id = players[0]
                    win_money = players_count * config.cfg.CitiesBet
                    await db.add_money(winner_id, win_money)

                    stats_lines = []
                    for n, (uid, count) in enumerate(
                        Cities.get_all_stat().items(), 1
                    ):
                        prefix = "👑 1" if n == 1 else str(n)
                        stats_lines.append(
                            f"{prefix}. **{await func.get_name(uid)}** назвал {count} городов",
                        )

                    stat_text = "\n".join(stats_lines) or "Пусто!"
                    await client.send_message(
                        config.chats.chat,
                        phrase.cities.winner.format(
                            await func.get_name(winner_id),
                            formatter.value_to_str(
                                win_money - config.cfg.CitiesBet,
                                phrase.currency,
                            ),
                            stat_text,
                        ),
                        reply_to=config.chats.topics.games,
                    )
                    return Cities.end_game()

                global CitiesTimerTask
                CitiesTimerTask = asyncio.create_task(
                    cities_timeout(next_player, last_city),
                )
                return await client.send_message(
                    config.chats.chat,
                    phrase.cities.timeout_done.format(
                        player_name,
                        await func.get_name(next_player),
                        last_city.title(),
                    ),
                    reply_to=config.chats.topics.games,
                )

            if second % 5 == 0 and second <= config.cfg.CitiesTimeout / 2:
                text = phrase.cities.timeout.format(
                    player=player_name, time=second
                )
                if timer_msg:
                    try:
                        await timer_msg.edit(text)
                    except Exception:
                        timer_msg = await client.send_message(
                            config.chats.chat,
                            text,
                            reply_to=config.chats.topics.games,
                        )
                else:
                    timer_msg = await client.send_message(
                        config.chats.chat,
                        text,
                        reply_to=config.chats.topics.games,
                    )

            await asyncio.sleep(1)

    except asyncio.CancelledError:
        await _safe_delete(timer_msg)


@client.on(events.NewMessage(chats=config.chats.chat))
async def cities_answer(event: Message):
    if (
        not _check_topic(event)
        or event.text.startswith("/")
        or not Cities.get_game_status()
    ):
        return

    if event.sender_id not in Cities.get_players():
        return

    city = event.text.strip()
    result_code = Cities.answer(event.sender_id, city)

    async def autodelete(text: str):
        msg = await event.reply(text)
        await asyncio.sleep(config.cfg.CitiesAutodelete)
        await _safe_delete(msg)

    global CitiesTimerTask
    if result_code == 0:
        if CitiesTimerTask:
            CitiesTimerTask.cancel()

        current_player = Cities.who_answer()
        last_city = Cities.get_last_city()
        await event.reply(
            phrase.cities.city_accepted.format(
                last_city.title(),
                await func.get_name(current_player),
            ),
        )
        CitiesTimerTask = asyncio.create_task(
            cities_timeout(current_player, last_city)
        )

    elif result_code == 1:
        await autodelete(phrase.cities.unknown_city)
    elif result_code == 2:
        await autodelete(phrase.cities.not_your_turn)
    elif result_code == 4:
        req = formatter.city_last_letter(Cities.get_last_city()).upper()
        await autodelete(phrase.cities.wrong_letter.format(req))
    elif result_code == 5:
        await autodelete(phrase.cities.already_inlist)


@client.on(events.CallbackQuery(pattern=r"^cities\."))
async def cities_callback(event: events.CallbackQuery.Event):
    data = event.data.decode().split(".")
    action = data[1]

    if action == "join":
        if event.sender_id in Cities.get_players():
            return await event.answer(phrase.cities.already_ingame, alert=True)

        balance = await db.get_money(event.sender_id)
        if balance < config.cfg.PriceForCities:
            return await event.answer(
                phrase.money.not_enough.format(
                    formatter.value_to_str(balance, phrase.currency),
                ),
            )

        await db.add_money(event.sender_id, -config.cfg.PriceForCities)
        Cities.add_player(event.sender_id)

        names = [await func.get_name(pid) for pid in Cities.get_players()]
        keyboard = [
            [
                KeyboardButtonCallback(
                    text="➕ Присоединиться", data="cities.join"
                )
            ],
            [
                KeyboardButtonCallback(
                    text="🎮 Начать игру", data="cities.start"
                )
            ],
            [KeyboardButtonCallback(text="❌ Отменить", data="cities.cancel")],
        ]
        await event.edit(
            phrase.cities.start.format(", ".join(names)), buttons=keyboard
        )
        return await event.answer(phrase.cities.set_ingame)

    if action == "start":
        if len(Cities.get_players()) < 2:
            return await event.answer(phrase.cities.low_players, alert=True)

        Cities.start_game()
        curr = Cities.who_answer()
        global CitiesTimerTask
        CitiesTimerTask = asyncio.create_task(
            cities_timeout(curr, Cities.get_last_city()),
        )
        return await event.edit(
            phrase.cities.game_started.format(
                Cities.get_last_city().title(),
                await func.get_name(curr),
            ),
        )

    if action == "cancel":
        if event.sender_id not in Cities.get_players():
            return await event.answer(phrase.cities.not_in_players, alert=True)
        Cities.end_game()
        return await event.edit("❌ Игра отменена.")
    return None


@func.new_command(
    r"/(города|города старт|cities start|миниигра города|minigame cities|cities)$",
)
async def cities_start(event: Message):
    if event.chat_id != config.chats.chat:
        return await event.reply(phrase.cities.chat)
    if not _check_topic(event):
        return await event.reply(phrase.game_topic_warning)

    if Cities.get_players() or Cities.get_game_status():
        return await event.reply(
            phrase.cities.already_started,
            buttons=[
                [
                    KeyboardButtonCallback(
                        text="❌ Отменить", data="cities.cancel"
                    )
                ],
            ],
        )

    Cities.end_game()
    Cities.add_player(event.sender_id)

    keyboard = [
        [KeyboardButtonCallback(text="➕ Присоединиться", data="cities.join")],
        [KeyboardButtonCallback(text="🎮 Начать игру", data="cities.start")],
        [KeyboardButtonCallback(text="❌ Отменить", data="cities.cancel")],
    ]

    msg = await event.reply(
        phrase.cities.start.format(await func.get_name(event.sender_id)),
        buttons=keyboard,
    )

    current_id = Cities.get_id()
    await asyncio.sleep(300)
    if not Cities.get_game_status() and Cities.get_id() == current_id:
        await msg.edit(phrase.cities.wait_exceeded, buttons=None)
        Cities.end_game()
    return None


async def crocodile_onboot():
    if await CrocodileGame.is_running():
        client.add_event_handler(
            crocodile_handler,
            events.NewMessage(chats=config.chats.chat),
        )
        client.add_event_handler(
            crocodile_hint,
            events.NewMessage(pattern=r"(?i)^/подсказка$", func=func.checks),
        )
