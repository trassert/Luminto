import asyncio
from datetime import datetime
from random import choice, randint
from time import time
from typing import TYPE_CHECKING, Any

import aiofiles
from loguru import logger
from telethon import Button
from telethon import errors as tgerrors
from telethon.tl import types
from telethon.tl.types import (
    KeyboardButtonCallback,
)

from .. import (
    config,
    db,
    floodwait,
    formatter,
    mcrcon,
    mining,
    pathes,
    phrase,
    pic,
    states_helper,
    sys,
    nicks,
)
from . import func
from .client import aio, client

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


@func.new_command(r"/хост$")
@func.new_command(r"/host$")
@func.new_command(r"/айпи$")
@func.new_command(r"/ip")
async def host(event: Message) -> Message:
    """Выводит IP-адрес игрового сервера."""
    return await event.reply(phrase.server.host, link_preview=False)


@func.new_command(r"/помощь$")
@func.new_command(r"/help")
@func.new_command(r"/команды$")
@func.new_command(r"/commands$")
@func.new_command(r"команды$")
@func.new_command(r"бот помощь$")
async def help(event: Message) -> Message:
    """Выводит список доступных команд."""
    return await event.reply(phrase.help.comm, link_preview=False)


@func.new_command(r"/пинг(.*)")
@func.new_command(r"/ping(.*)")
@func.new_command(r"пинг(.*)")
async def ping(event: Message) -> Message:
    """Проверяет задержку бота и (опционально) сервера."""
    arg: str = event.pattern_match.group(1).strip().lower()
    latency: float = round(time() - event.date.timestamp(), 2)
    latency_text: str = (
        phrase.ping.min if latency <= 0 else f"за {latency} сек."
    )

    extra_pings: list[str] = []
    if arg in [
        "all",
        "подробно",
        "подробный",
        "полн",
        "полный",
        "весь",
        "фулл",
        "full",
    ]:
        try:
            async with mcrcon.Vanilla as rcon:
                pings = formatter.parse_pings_strict(
                    formatter.rm_colors(await rcon.send("ping @a"))
                )
            if pings == []:
                extra_pings.append("🧍 : Игроков не найдено")
            else:
                extra_pings.append(
                    f"🧍 : Пинг игроков ↑|≈|↓ - {max(pings)} | {sum(pings) // len(pings)} | {min(pings)} мс"
                )
        except Exception:
            extra_pings.append("🧍 : Не удалось получить пинг игроков")

    text: str = (
        f"{phrase.ping.set.format(latency_text)}\n{'\n'.join(extra_pings)}"
    )
    return await event.reply(text)


@func.new_command(r"/start$")
@func.new_command(r"/старт$")
async def start(event: Message) -> Message:
    """Приветственное сообщение при первом запуске."""
    name: str = await func.get_name(event.sender_id)
    return await event.reply(phrase.start.format(name), silent=True)


@func.new_command(r"/обо мне$")
@func.new_command(r"/я$")
@func.new_command(r"/i$")
@func.new_command(r"/profile")
@func.new_command(r"/профиль$")
@func.new_command(r"/myprofile")
async def profile(event: Message) -> Message:
    """Выводит детальную информацию об игроке, его роли, государстве и статистике."""
    user_id: int = event.sender_id
    role: int = await db.Roles().get(user_id)

    state_author: str | bool = states_helper.if_author(user_id)
    if state_author:
        state_info = f"**{state_author}, Глава**"
    else:
        state_player: str | bool = states_helper.if_player(user_id)
        state_info = state_player or "Не состоит в государстве"

    nick: str = await nicks.get_byid(user_id) or "Не привязан"

    if nick != "Не привязан":
        m_day: int = await db.Statistic(1).get(nick)
        m_week: int = await db.Statistic(7).get(nick)
        m_month: int = await db.Statistic(30).get(nick)
        m_all: int = await db.Statistic().get(nick, all_days=True)

        try:
            async with mcrcon.Vanilla as rcon:
                raw_time: str = await rcon.send(
                    f"papi parse --null %PTM_playtime_{nick}:luminto%",
                )
                time_played: str = raw_time.replace("\n", "").strip()
                if time_played == "":
                    time_played = "Менее минуты"
        except Exception:
            time_played = "Неизвестно"
    else:
        m_day = m_week = m_month = m_all = 0
        time_played = "-"

    balance: int = await db.get_money(user_id)

    return await event.reply(
        phrase.profile.full.format(
            name=await func.get_name(user_id),
            minecraft=nick,
            role_name=phrase.roles.types[role],
            role_number=role,
            state=state_info,
            m_day=m_day,
            m_week=m_week,
            m_month=m_month,
            m_all=m_all,
            balance=formatter.value_to_str(balance, phrase.currency),
            time=time_played,
        ),
    )


@func.new_command(r"/time")
@func.new_command(r"/время$")
@func.new_command(r"/мск$")
@func.new_command(r"/msk$")
async def msktime(event: Message) -> Message:
    """Показывает текущее московское время."""
    return await event.reply(
        phrase.time.format(datetime.now().strftime("%H:%M:%S"))
    )


@func.new_command(r"(/г )?(шахта|майнить|копать)$")
@func.new_command(r"/mine")
@func.new_command(r"/(шахта|майнить|копать)$")
async def mine_start(event: Message) -> Message:
    """Запускает сессию майнинга (шахты)."""
    user_id: int = event.sender_id

    if not (
        states_helper.if_player(user_id) or states_helper.if_author(user_id)
    ):
        return await event.reply(phrase.mine.not_in_state)
    if not await db.ready_to_mine(user_id):
        return await event.reply(choice(phrase.mine.not_ready))
    if user_id in mining.sessions:
        return await event.reply(phrase.mine.already)

    initial: int = randint(1, config.cfg.Mining.InitialGems)
    mining.sessions[user_id] = {
        "gems": initial,
        "death_chance": config.cfg.Mining.BaseDeathChance,
        "step": 1,
    }

    asyncio.create_task(mining.cleanup_session(user_id))

    buttons = [
        [Button.inline(phrase.mine.button_yes, f"mine.yes.{user_id}")],
        [Button.inline(phrase.mine.button_no, f"mine.no.{user_id}")],
    ]

    msg_text: str = (
        phrase.mine.done.format(
            formatter.value_to_str(initial, phrase.currency)
        )
        + phrase.mine.q
    )
    return await event.reply(msg_text, buttons=buttons)


@func.new_command(r"/nick(.*)")
@func.new_command(r"/ник(.*)")
async def check_nick(event: Message) -> Message:
    """Показывает привязанный Minecraft ник пользователя."""
    arg: str = event.pattern_match.group(1).strip()
    user_id: int = None

    if arg:
        try:
            user_id = await func.get_id(arg)
        except Exception:
            user_id = await func.get_author_by_msgid(
                event.chat_id,
                func.get_reply_message_id(event),
            )
    else:
        user_id = await func.get_author_by_msgid(
            event.chat_id,
            func.get_reply_message_id(event),
        )

    if user_id is None:
        author_nick: str = await nicks.get_byid(event.sender_id)
        if author_nick is None:
            return await event.reply(phrase.nick.who)
        return await event.reply(phrase.nick.urnick.format(author_nick))

    nick: str = await nicks.get_byid(user_id)
    return await event.reply(
        phrase.nick.no_nick
        if nick is None
        else phrase.nick.usernick.format(nick),
    )


@func.new_command(r"/скинуть(.*)")
@func.new_command(r"/кинуть(.*)")
@func.new_command(r"/дать(.*)")
@func.new_command(r"/перевести(.*)")
@func.new_command(r"перевести(.*)")
async def swap_money(event: Message) -> Message:
    """Переводит валюту другому игроку."""
    args: list[str] = event.pattern_match.group(1).strip().split()
    if not args:
        return await event.reply(
            phrase.money.no_count + phrase.money.swap_balance_use
        )

    sender_id: int = event.sender_id

    try:
        recipient_id: int = await func.swap_resolve_recipient(event, args)
    except ValueError, TypeError, tgerrors.rpcerrorlist.UsernameInvalidError:
        return await event.reply(
            phrase.money.no_such_people + phrase.money.swap_balance_use,
        )

    if recipient_id is None:
        return await event.reply(
            phrase.money.no_people + phrase.money.swap_balance_use
        )

    if sender_id == recipient_id:
        return await event.reply(phrase.money.selfbyself)

    try:
        entity = await client.get_entity(recipient_id)
        if isinstance(entity, types.User) and entity.bot:
            return await event.reply(phrase.money.bot)
    except Exception:
        return await event.reply(
            phrase.money.no_people + phrase.money.swap_balance_use
        )

    if args[0].lower() in {"все", "всё", "all", "весь"}:
        sender_balance = await db.get_money(sender_id)
        amount = sender_balance
    else:
        try:
            amount = int(args[0])
        except ValueError:
            return await event.reply(
                phrase.money.nan_count + phrase.money.swap_balance_use
            )

    if amount <= 0:
        return await event.reply(phrase.money.negative_count)

    current_balance = await db.get_money(sender_id)

    if current_balance < amount:
        return await event.reply(
            phrase.money.not_enough.format(
                formatter.value_to_str(current_balance, phrase.currency),
            ),
        )

    await db.add_money(sender_id, -amount)
    await db.add_money(recipient_id, amount)

    return await event.reply(
        phrase.money.swap_money.format(
            formatter.value_to_str(amount, phrase.currency)
        ),
    )


@func.new_command(r"/вывести (.+)")
@func.new_command(r"/вывод (.+)")
@func.new_command(r"/вмайн (.+)")
@func.new_command(r"/в майн (.+)")
@func.new_command(r"/вмаин (.+)")
@func.new_command(r"/в маин (.+)")
@func.new_command(r"вывести (.+)")
async def money_to_server(event: Message) -> Message:
    user_id: int = event.sender_id
    nick: str = await nicks.get_byid(user_id)

    if nick is None:
        return await event.reply(phrase.nick.not_append)

    try:
        amount: int = int(event.pattern_match.group(1).strip())
    except ValueError:
        return await event.reply(phrase.money.nan_count)

    if amount < 1:
        return await event.reply(phrase.money.negative_count)

    daily_limit = 64
    if amount > daily_limit:
        return await event.reply(phrase.bank.daily_limit)

    success, remaining = await db.check_and_update_withdraw_limit(
        user_id, amount
    )

    if not success:
        return await event.reply(
            phrase.bank.limit.format(
                formatter.value_to_str(remaining, phrase.currency)
            ),
        )

    balance = await db.get_money(user_id)

    if balance < amount:
        await db.rollback_withdraw_limit(user_id, amount)
        return await event.reply(
            phrase.money.not_enough.format(
                formatter.value_to_str(balance, phrase.currency)
            ),
        )

    await db.add_money(user_id, -amount)

    try:
        async with mcrcon.Vanilla as rcon:
            await rcon.send(f"invgive {nick} amethyst_shard {amount}")
    except Exception as e:
        logger.error(f"RCON Error during withdraw: {e}")

        await db.add_money(user_id, amount)
        await db.rollback_withdraw_limit(user_id, amount)

        return await event.reply(phrase.bank.error)

    return await event.reply(
        phrase.bank.withdraw.format(
            formatter.value_to_str(amount, phrase.currency)
        ),
    )


@func.new_command(r"/вывести$")
@func.new_command(r"/вывод$")
@func.new_command(r"/вмайн$")
@func.new_command(r"/в майн$")
@func.new_command(r"/вмаин$")
@func.new_command(r"/в маин$")
@func.new_command(r"вывести$")
async def money_to_server_empty(event: Message) -> Message:
    return await event.reply(phrase.money.no_count)


@func.new_command(r"/аметисты$")
@func.new_command(r"/баланс$")
@func.new_command(r"баланс$")
@func.new_command(r"/wallet")
@func.new_command(r"wallet$")
@func.new_command(r"/мой баланс$")
@func.new_command(r"мой баланс$")
async def get_balance(event: Message) -> Message:
    """Показывает баланс аметистов игрока."""
    balance: int = await db.get_money(event.sender_id)
    return await event.reply(
        phrase.money.wallet.format(
            formatter.value_to_str(balance, phrase.currency)
        ),
    )


@func.new_command(r"/linknick (\S+)\s*(\S*)$")
@func.new_command(r"/привязать (\S+)\s*(\S*)$")
@func.new_command(r"привязать (\S+)\s*(\S*)$")
@func.new_command(r"/новый ник (\S+)\s*(\S*)$")
@func.new_command(r"/линкник (\S+)\s*(\S*)$")
async def link_nick(event: Message) -> Message:
    """Привязывает Minecraft ник к Telegram аккаунту и добавляет в WhiteList."""

    nick: str = event.pattern_match.group(1).strip()
    ref_code: str = event.pattern_match.group(2).strip()
    sender_id: int = event.sender_id

    if formatter.is_valid_mc_nick(nick) is False:
        return await event.reply(phrase.nick.invalid)

    current_linked_nick = await nicks.get_byid(sender_id)
    if current_linked_nick == nick:
        return await event.reply(phrase.nick.already_you)
    if await nicks.get_byname(nick) is not None:
        return await event.reply(phrase.nick.taken)

    if current_linked_nick is not None:
        btn = [
            KeyboardButtonCallback(
                "✅ Сменить", f"nick.{nick}.{sender_id}".encode()
            ),
        ]
        price_str = formatter.value_to_str(
            config.cfg.PriceForChangeNick,
            phrase.currency,
        )
        return await event.reply(
            phrase.nick.already_have.format(price=price_str),
            buttons=[btn],
        )

    try:
        async with mcrcon.Vanilla as rcon:
            await rcon.send(f"nwl add name {nick}")
    except Exception:
        logger.error("RCON: Ошибка при добавлении в белый список")
        return await event.reply(phrase.nick.error)

    ref_msg = ""
    if ref_code:
        ref_author_id = await db.RefCodes().check_ref(ref_code)
        if ref_author_id:
            await db.RefCodes().add_uses(ref_author_id, sender_id)
            await db.add_money(ref_author_id, config.cfg.RefGift)
            await db.add_money(sender_id, config.cfg.RefGift)
            ref_msg = phrase.ref.gift.format(config.cfg.RefGift)

            try:
                sender_name = await func.get_name(sender_id, minecraft=True)
                await client.send_message(
                    int(ref_author_id),
                    phrase.ref.used.format(
                        user=sender_name, amount=config.cfg.RefGift
                    ),
                )
            except Exception:
                pass

    await db.add_money(sender_id, config.cfg.LinkGift)
    await nicks.link(sender_id, nick)

    await event.reply(
        phrase.nick.success.format(
            formatter.value_to_str(config.cfg.LinkGift, phrase.currency),
        ),
    )
    if ref_msg:
        await event.reply(ref_msg)
    logger.success(f"Юзер {sender_id} привязал свой ник!")
    if current_linked_nick is None:
        await event.reply(phrase.nick.referrals, link_preview=False)
    try:
        return await aio.approve_chat_join_request(
            chat_id=config.chats.chat, user_id=sender_id
        )
    except Exception:
        logger.info(
            f"Игрок {sender_id} привязал ник, но заявки нет. Пропускаю..."
        )


@func.new_command(r"/linknick$")
@func.new_command(r"/привязать$")
@func.new_command(r"привязать$")
@func.new_command(r"/новый ник$")
@func.new_command(r"/линкник$")
async def link_nick_empty(event: Message) -> Message:
    return await event.reply(phrase.nick.not_select)


@func.new_command(r"/серв$")
@func.new_command(r"/сервер")
@func.new_command(r"/server")
async def sysinfo(event: Message) -> Message:
    """Выводит системную информацию о хосте бота."""
    return await event.reply(await sys.get_info())


@func.new_command(r"/randompic")
@func.new_command(r"/рандомпик$")
@func.new_command(r"/картинка$")
async def randompic(event: Message) -> Message:
    """Отправляет случайную картинку с учетом Flood-контроля."""
    wait_time = floodwait.WaitPic.request()
    if wait_time is False:
        return await event.reply(phrase.pic.wait)

    await asyncio.sleep(wait_time)
    return await client.send_file(
        entity=event.chat_id,
        file=pic.get_random(),
        reply_to=event.id,
        caption=phrase.pic.get,
    )


@func.new_command(r"/map")
@func.new_command(r"/мап$")
@func.new_command(r"/карта$")
async def getmap(event: Message) -> Message:
    """Выводит ссылку на онлайн-карту сервера."""
    return await event.reply(phrase.get_map, link_preview=False)


@func.new_command(r"/vote@luminto_chatbot$")
@func.new_command(r"/vote$")
@func.new_command(r"/голос$")
@func.new_command(r"/голосование$")
@func.new_command(r"/проголосовать$")
async def vote(event: Message) -> Message:
    """Выводит ссылку на мониторинги для голосования."""
    return await client.send_message(
        event.chat_id,
        message=phrase.vote,
        reply_to=event.id,
        link_preview=False,
    )


@func.new_command(r"/нпоиск (.+)")
@func.new_command(r"/пник (.+)")
@func.new_command(r"/игрок (.+)")
@func.new_command(r"/поискпонику (.+)")
@func.new_command(r"игрок (.+)")
@func.new_command(r"нпоиск (.+)")
@func.new_command(r"пник (.+)")
async def check_info_by_nick(event: Message) -> Message:
    """Ищет Telegram-профиль и статус игрока по его Minecraft нику."""
    nick: str = event.pattern_match.group(1).strip()
    user_id: int = await nicks.get_byname(nick)

    if user_id is None:
        return await event.reply(phrase.nick.not_find)

    state: str | bool = states_helper.if_player(
        user_id
    ) or states_helper.if_author(user_id)
    state_info = state or "Нет"

    return await event.reply(
        phrase.nick.info.format(
            tg=await func.get_name(user_id),
            role=phrase.roles.types[await db.Roles().get(user_id)],
            state=state_info,
        ),
    )


@func.new_command(r"/нпоиск$")
@func.new_command(r"/пник$")
@func.new_command(r"/игрок$")
@func.new_command(r"/поискпонику$")
@func.new_command(r"игрок$")
@func.new_command(r"нпоиск$")
@func.new_command(r"пник$")
async def check_info_by_nick_empty(event: Message) -> Message:
    return await event.reply(phrase.nick.empty)


@func.new_command(r"\+город (.+)")
async def cities_request(event: Message) -> Message:
    """Отправляет запрос администратору на добавление нового города."""
    word: str = event.pattern_match.group(1).strip().lower()

    async with aiofiles.open(pathes.chk_city) as aiof:
        if word in (await aiof.read()).splitlines():
            return await event.reply(phrase.cities.exists)
    async with aiofiles.open(pathes.bl_city) as aiof:
        if word in (await aiof.read()).splitlines():
            return await event.reply(phrase.cities.in_blacklist)

    user_name: str = await func.get_name(event.sender_id)
    keyboard = [
        [
            KeyboardButtonCallback(
                "✅ Добавить",
                f"cityadd.yes.{word}.{event.sender_id}".encode(),
            ),
            KeyboardButtonCallback(
                "❌ Отклонить",
                f"cityadd.no.{word}.{event.sender_id}".encode(),
            ),
        ],
    ]

    try:
        await client.send_message(
            config.tokens.bot.creator,
            phrase.cities.request.format(user=user_name, word=word),
            buttons=keyboard,
        )
    except tgerrors.ButtonDataInvalidError:
        return await event.reply(phrase.cities.long)
    return await event.reply(phrase.cities.set.format(word=word))


@func.new_command(r"\+города\s([\s\S]+)")
async def cities_requests(event: Message) -> Message:
    """Массовая проверка и отправка запросов на добавление городов."""
    words: list[str] = [
        w.strip().lower()
        for w in event.pattern_match.group(1).splitlines()
        if w.strip()
    ]
    if not words:
        return await event.reply(phrase.cities.empty_long)

    status_msg = await event.reply(phrase.cities.checker)

    async with aiofiles.open(pathes.chk_city) as aiof:
        existing = set((await aiof.read()).splitlines())
    async with aiofiles.open(pathes.bl_city) as aiof:
        blacklisted = set((await aiof.read()).splitlines())

    output_lines: list[str] = []
    pending_to_admin: list[str] = []

    for word in words:
        if word in existing:
            output_lines.append(f"Город **{word}** - есть")
        elif word in blacklisted:
            output_lines.append(f"Город **{word}** - в ЧС")
        else:
            pending_to_admin.append(word)
            output_lines.append(f"Город **{word}** - проверяется")

        if len(output_lines) % 5 == 0:
            await status_msg.edit("\n".join(output_lines))
            await asyncio.sleep(0.5)

    await status_msg.edit("\n".join(output_lines))

    user_name = await func.get_name(event.sender_id)
    for word in pending_to_admin:
        btns = [
            [
                KeyboardButtonCallback(
                    "✅ Добавить",
                    f"cityadd.yes.{word}.{event.sender_id}".encode(),
                ),
                KeyboardButtonCallback(
                    "❌ Отклонить",
                    f"cityadd.no.{word}.{event.sender_id}".encode(),
                ),
            ],
        ]
        try:
            await client.send_message(
                config.tokens.bot.creator,
                phrase.cities.request.format(user=user_name, word=word),
                buttons=btns,
            )
            await asyncio.sleep(0.3)
        except Exception:
            pass
    return None


@func.new_command(r"\-город (.+)")
async def cities_remove(event: Message) -> Message:
    """Удаляет город из базы (доступно администраторам)."""
    roles = db.Roles()
    if await roles.get(event.sender_id) < roles.ADMIN:
        return await event.reply(
            phrase.roles.no_perms.format(
                level=roles.ADMIN, name=phrase.roles.admin
            ),
        )

    word: str = event.pattern_match.group(1).strip().lower()
    async with aiofiles.open(pathes.chk_city) as aiof:
        lines = (await aiof.read()).splitlines()

    if word not in lines:
        return await event.reply(phrase.cities.not_exists)

    lines.remove(word)
    async with aiofiles.open(pathes.chk_city, "w") as aiof:
        await aiof.write("\n".join(lines))
    return await event.reply(phrase.cities.deleted.format(word))


@func.new_command(r"/rules")
@func.new_command(r"/правила$")
@func.new_command(r"/правилачата$")
@func.new_command(r"/правила сервера$")
@func.new_command(r"rules")
@func.new_command(r"правила$")
async def rules(event: Message) -> Message:
    """Выводит правила сервера/чата."""
    return await event.reply(phrase.rules.base, link_preview=False)


@func.new_command(r"онлайн$")
@func.new_command(r"/онлайн$")
@func.new_command(r"online$")
@func.new_command(r"/online")
async def online(event: Message) -> Message:
    """Запрашивает список игроков онлайн через RCON."""
    try:
        async with mcrcon.Vanilla as rcon:
            response: str = await rcon.send("list")

        players_raw: str = (
            response.split(":", 1)[1].strip() if ":" in response else ""
        )
        players: list[str] = [
            p.strip() for p in players_raw.split(",") if p.strip()
        ]

        return await event.reply(
            phrase.online.format(list=", ".join(players), count=len(players)),
        )
    except Exception as e:
        logger.error(f"RCON Error during online list: {e}")
        return await event.reply(
            "❌ Не удалось получить список игроков (сервер недоступен).",
        )


@func.new_command(r"/newhint")
@func.new_command(r"/addhint")
async def add_new_hint(event: Message) -> Message:
    """Запускает диалог для добавления новой подсказки к слову в игре Крокодил."""
    if not event.is_private:
        return await event.reply(phrase.newhints.private)

    word: str = await db.get_crocodile_word()
    async with client.conversation(event.sender_id, timeout=300) as conv:
        await conv.send_message(phrase.newhints.ask_hint.format(word=word))

        try:
            while True:
                response: Message = await conv.get_response()
                text: str = response.raw_text.strip()

                if text.lower() == "/стоп":
                    return await conv.send_message(phrase.newhints.cancel)
                if text.startswith("/"):
                    continue

                hint_cap = text.capitalize()
                pending_id = await db.add_pending_hint(
                    event.sender_id, hint_cap, word
                )

                admin_btns = [
                    [
                        Button.inline("✅", f"hint.accept.{pending_id}"),
                        Button.inline("❌", f"hint.reject.{pending_id}"),
                    ],
                ]
                await client.send_message(
                    config.tokens.bot.creator,
                    phrase.newhints.admin_alert.format(
                        word=word,
                        hint=hint_cap,
                        user=await func.get_name(event.sender_id),
                    ),
                    buttons=admin_btns,
                )
                return await conv.send_message(
                    phrase.newhints.sent.format(pending_id)
                )
        except TimeoutError:
            return await event.reply(phrase.newhints.timeout)


@func.new_command(r"/gethint")
async def get_last_hint(event: Message) -> Message:
    """Выводит последнюю предложенную подсказку для модерации (только для админов)."""
    if not event.is_private:
        return await event.reply(phrase.newhints.private)

    roles = db.Roles()
    if await roles.get(event.sender_id) < roles.ADMIN:
        return await event.reply(
            phrase.roles.no_perms.format(
                level=roles.ADMIN, name=phrase.roles.admin
            ),
        )

    hint: dict[str, Any] = await db.get_latest_pending_hint()
    if not hint:
        return await event.reply(phrase.newhints.not_found)

    btns = [
        [
            Button.inline("✅", f"hint.accept.{hint['id']}"),
            Button.inline("❌", f"hint.reject.{hint['id']}"),
        ],
    ]

    return await event.reply(
        phrase.newhints.admin_alert.format(
            word=hint["word"],
            hint=hint["hint"],
            user=await func.get_name(hint["user"]),
        ),
        buttons=btns,
    )
