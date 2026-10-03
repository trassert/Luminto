import asyncio
import contextlib
from random import choice, random
from typing import TYPE_CHECKING

from loguru import logger
from telethon import Button, events

from .. import config, crocostat, db, files, formatter, pathes, phrase
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
    return await event.reply(
        phrase.casino.start.format(config.cfg.PriceForCasino),
        buttons=[
            [Button.inline("🎰 Автоматическая прокрутка", b"casino.auto")]
        ],
    )


@func.new_command([r"/крокодил$", r"/crocodile$", r"старт крокодил$"])
async def crocodile(event: Message):
    if event.chat_id != config.chats.chat:
        return await event.reply(phrase.crocodile.chat)
    if not _check_topic(event):
        return await event.reply(phrase.game_topic_warning)
    stop_btn = Button.inline("❌ Остановить игру", b"crocodile.stop")
    if not await CrocodileGame.is_running():
        return await event.reply(
            phrase.crocodile.game,
            buttons=[
                [Button.inline("✅ Играть", b"crocodile.start"), stop_btn]
            ],
        )
    return await event.reply(phrase.crocodile.no, buttons=[[stop_btn]])


@func.new_command([r"/ставка(.*)", r"/крокоставка(.*)"])
async def crocodile_bet(event: Message):
    if not _check_topic(event):
        return await event.reply(phrase.game_topic_warning)

    raw_bet = event.pattern_match.group(1).strip()
    min_bet, max_bet = config.cfg.Crocodile.MinBet, config.cfg.Crocodile.MaxBet

    try:
        bet = int(raw_bet) if raw_bet else min_bet
    except ValueError:
        return await event.reply(phrase.money.nan_count)

    if bet < min_bet:
        return await event.reply(
            phrase.money.min_count.format(
                formatter.value_to_str(min_bet, phrase.currency)
            )
        )
    if bet > max_bet:
        return await event.reply(
            phrase.money.max_count.format(
                formatter.value_to_str(max_bet, phrase.currency)
            )
        )
    if await CrocodileGame.is_running():
        return await event.reply(phrase.crocodile.no)

    sender_balance = await db.get_money(event.sender_id)
    if sender_balance < bet:
        return await event.reply(
            phrase.money.not_enough.format(
                formatter.value_to_str(sender_balance, phrase.currency)
            )
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
        )
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
        top_players = list((await crocostat.get_all()).keys())[
            : config.cfg.TopLowerBets
        ]

        total_payout = sum(
            round(
                bet_val
                * (
                    config.cfg.TopBets
                    if uid in top_players
                    else config.cfg.CrocodileBetCoo
                )
            )
            if str(event.sender_id) == uid
            else bet_val
            for uid, bet_val in bets.items()
        )

        win_msg = ""
        if total_payout > 0:
            await db.add_money(event.sender_id, total_payout)
            win_msg = phrase.crocodile.bet_win.format(
                formatter.value_to_str(total_payout, phrase.currency)
            )

        await CrocodileGame.stop_game()
        await CrocodileGame.set_last_hint(0)
        client.remove_event_handler(crocodile_hint)
        client.remove_event_handler(crocodile_handler)
        await crocostat.add(event.sender_id)
        return await event.reply(
            phrase.crocodile.win.format(current_word) + win_msg
        )

    if not text.startswith("/"):
        changed, new_mask_str, _finished = await CrocodileGame.reveal_on_guess(
            text
        )
        if changed:
            return await event.reply(
                phrase.crocodile.new.format(new_mask_str.replace("_", ".."))
            )
    return None


async def crocodile_hint(event: Message):
    if not _check_topic(event):
        return await event.reply(phrase.game_topic_warning)
    if not CrocodileGame.get_current():
        return None
    if not await CrocodileGame.add_hint(event.sender_id):
        return await event.reply(phrase.crocodile.hints_all)

    game = CrocodileGame.get_current()
    word = game["word"]
    if (
        random() < config.cfg.PercentForRandomLetter
        and len(game.get("hints", [])) > 1
    ):
        for i, letter in enumerate(game["unsec"], 1):
            if letter == "_":
                return await event.reply(
                    f"{i} буква в слове - **{word[i - 1]}**"
                )

    try:
        mapping = await files.load_json_async(pathes.crocomap)
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

                players_count = Cities.get_count_players()
                next_player = Cities.rem_player(current_player)

                if next_player is None:
                    remaining = Cities.get_players()
                    winner_id = remaining[0] if remaining else current_player
                    win_money = players_count * config.cfg.CitiesBet

                    stat_snapshot = Cities.get_all_stat()
                    Cities.end_game()
                    await db.add_money(winner_id, win_money)

                    stat_text = (
                        "\n".join(
                            [
                                f"{'👑 1' if n == 1 else n}. "
                                f"**{await func.get_name(uid)}** назвал {count} городов"
                                for n, (uid, count) in enumerate(
                                    stat_snapshot.items(), 1
                                )
                            ]
                        )
                        or "Пусто!"
                    )

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
                    return None

                global CitiesTimerTask
                CitiesTimerTask = asyncio.create_task(
                    cities_timeout(next_player, last_city)
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
                try:
                    timer_msg = await (
                        timer_msg.edit(text)
                        if timer_msg
                        else client.send_message(
                            config.chats.chat,
                            text,
                            reply_to=config.chats.topics.games,
                        )
                    )
                except Exception:
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
        or event.sender_id not in Cities.get_players()
    ):
        return

    async def autodelete(text: str):
        msg = await event.reply(text)
        await asyncio.sleep(config.cfg.CitiesAutodelete)
        await _safe_delete(msg)

    global CitiesTimerTask
    result_code = Cities.answer(event.sender_id, event.text.strip())

    if result_code == 0:
        if CitiesTimerTask:
            CitiesTimerTask.cancel()
        current_player = Cities.who_answer()
        last_city = Cities.get_last_city()
        await event.reply(
            phrase.cities.city_accepted.format(
                last_city.title(), await func.get_name(current_player)
            )
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
    action = event.data.decode().split(".")[1]

    if action == "join":
        if Cities.get_game_status():
            return await event.answer(phrase.cities.already_started, alert=True)
        if event.sender_id in Cities.get_players():
            return await event.answer(phrase.cities.already_ingame, alert=True)

        balance = await db.get_money(event.sender_id)
        if balance < config.cfg.PriceForCities:
            return await event.answer(
                phrase.money.not_enough.format(
                    formatter.value_to_str(balance, phrase.currency)
                )
            )

        await db.add_money(event.sender_id, -config.cfg.PriceForCities)
        Cities.add_player(event.sender_id)

        names = [await func.get_name(pid) for pid in Cities.get_players()]
        await event.edit(
            phrase.cities.start.format(", ".join(names)),
            buttons=[
                [Button.inline("➕ Присоединиться", "cities.join")],
                [Button.inline("🎮 Начать игру", "cities.start")],
                [Button.inline("❌ Отменить", "cities.cancel")],
            ],
        )
        return await event.answer(phrase.cities.set_ingame)

    if action == "start":
        if Cities.get_game_status():
            return await event.answer(phrase.cities.already_started, alert=True)
        if len(Cities.get_players()) < 2:
            return await event.answer(phrase.cities.low_players, alert=True)

        Cities.start_game()
        curr = Cities.who_answer()
        global CitiesTimerTask
        if CitiesTimerTask:
            CitiesTimerTask.cancel()
        CitiesTimerTask = asyncio.create_task(
            cities_timeout(curr, Cities.get_last_city())
        )
        return await event.edit(
            phrase.cities.game_started.format(
                Cities.get_last_city().title(), await func.get_name(curr)
            )
        )

    if action == "cancel":
        if event.sender_id not in Cities.get_players():
            return await event.answer(phrase.cities.not_in_players, alert=True)
        if Cities.get_game_status():
            return await event.answer(phrase.cities.already_started, alert=True)
        for pid in Cities.get_players():
            await db.add_money(pid, config.cfg.PriceForCities)
        if CitiesTimerTask:
            CitiesTimerTask.cancel()
        Cities.end_game()
        return await event.edit("❌ Игра отменена.")
    return None


@func.new_command(
    r"/(города|города старт|cities start|миниигра города|minigame cities|cities)$"
)
async def cities_start(event: Message):
    if event.chat_id != config.chats.chat:
        return await event.reply(phrase.cities.chat)
    if not _check_topic(event):
        return await event.reply(phrase.game_topic_warning)

    if Cities.get_players() or Cities.get_game_status():
        return await event.reply(
            phrase.cities.already_started,
            buttons=[[Button.inline("❌ Отменить", "cities.cancel")]],
        )

    Cities.end_game()
    Cities.add_player(event.sender_id)

    msg = await event.reply(
        phrase.cities.start.format(await func.get_name(event.sender_id)),
        buttons=[
            [Button.inline("➕ Присоединиться", "cities.join")],
            [Button.inline("🎮 Начать игру", "cities.start")],
            [Button.inline("❌ Отменить", "cities.cancel")],
        ],
    )

    current_id = Cities.get_id()
    await asyncio.sleep(300)
    if (
        not Cities.get_game_status()
        and Cities.get_id() == current_id
        and Cities.get_count_players() <= 1
    ):
        await msg.edit(phrase.cities.wait_exceeded, buttons=None)
        Cities.end_game()
    return None


async def crocodile_onboot():
    if await CrocodileGame.is_running():
        client.add_event_handler(
            crocodile_handler, events.NewMessage(chats=config.chats.chat)
        )
        client.add_event_handler(
            crocodile_hint,
            events.NewMessage(pattern=r"(?i)^/подсказка$", func=func.checks),
        )
