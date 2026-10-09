import asyncio
import contextlib
from datetime import datetime
from random import choice, randint
from time import time
from typing import TYPE_CHECKING, Any

import aiofiles
import aiohost
import anyio
from loguru import logger
from telethon import Button
from telethon import errors as tgerrors
from telethon.tl import types

from .. import (
    config,
    db,
    files,
    floodwait,
    formatter,
    mcrcon,
    minimessage,
    mining,
    nicks,
    pathes,
    phrase,
    pic,
    referrals,
    roles,
    states_helper,
    sys,
)
from . import func
from .client import aio, client

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


@func.new_command([r"/хост$", r"/host$", r"/айпи$", r"/ip"])
async def host(event: Message) -> Message:
    """Выводит IP-адрес игрового сервера."""
    return await event.reply(phrase.server.host, link_preview=False)


@func.new_command(
    [
        r"/помощь$",
        r"/help",
        r"/команды$",
        r"/commands$",
        r"команды$",
        r"бот помощь$",
    ],
)
async def help(event: Message) -> Message:
    """Выводит список доступных команд."""
    return await event.reply(phrase.help.comm, link_preview=False)


@func.new_command([r"/пинг(.*)", r"/ping(.*)", r"пинг(.*)"])
async def ping(event: Message) -> Message:
    """Проверяет задержку бота и (опционально) сервера."""
    arg = event.pattern_match.group(1).strip().lower()
    latency = round(time() - event.date.timestamp(), 2)
    latency_text = phrase.ping.min if latency <= 0 else f"за {latency} сек."
    extra = []

    if arg in {
        "all",
        "подробно",
        "подробный",
        "полн",
        "полный",
        "весь",
        "фулл",
        "full",
    }:
        try:
            async with mcrcon.Vanilla as rcon:
                pings = formatter.parse_pings_strict(
                    formatter.rm_colors(await rcon.send("ping @a")),
                )
            extra.append(
                "🧍 : Игроков не найдено"
                if not pings
                else f"🧍 : Пинг игроков ↑|≈|↓ - {max(pings)} | {sum(pings) // len(pings)} | {min(pings)} мс",
            )
        except Exception:
            extra.append("🧍 : Не удалось получить пинг игроков")

    return await event.reply(
        f"{phrase.ping.set.format(latency_text)}\n{'\n'.join(extra)}",
    )


@func.new_command([r"/start(.*)", r"/старт(.*)"])
async def start(event: Message):
    """Приветственное сообщение при первом запуске."""
    await event.reply(
        phrase.start.format(await func.get_name(event.sender_id)),
        silent=True,
    )
    arg = event.pattern_match.group(1).strip().lower()
    if not arg.isdigit():
        return
    referral_id = int(arg)
    if referral_id == event.sender_id or not await referrals.new(
        referral_id, event.sender_id
    ):
        return
    try:
        await client.send_message(
            referral_id,
            phrase.ref.start_withref.format(
                await func.get_name(event.sender_id)
            ),
        )
    except Exception:
        logger.warning(f"Не удалось отправить сообщение рефералу {referral_id}")


@func.new_command(
    [r"/обо мне$", r"/я$", r"/i$", r"/profile", r"/профиль$", r"/myprofile"],
)
async def profile(event: Message) -> Message:
    """Выводит детальную информацию об игроке, его роли, государстве и статистике."""
    user_id = event.sender_id
    minecraft_nick = await nicks.get_byid(user_id)
    role = (
        await roles.get_role(minecraft_nick)
        if minecraft_nick
        else roles.DEFAULT
    )

    if state_author := await states_helper.if_author(user_id):
        state_info = f"**{state_author}, Глава**"
    elif state_deputy := await states_helper.if_deputy(user_id):
        state_info = f"**{state_deputy}, Заместитель**"
    else:
        state_info = (
            await states_helper.if_player(user_id)
        ) or "Не состоит в государстве"

    nick = minecraft_nick or "Не привязан"

    if nick != "Не привязан":
        m_day = await db.Statistic(1).get(nick)
        m_week = await db.Statistic(7).get(nick)
        m_month = await db.Statistic(30).get(nick)
        m_all = await db.Statistic().get(nick, all_days=True)
        try:
            async with mcrcon.Vanilla as rcon:
                time_played = (
                    await rcon.send(
                        f"papi parse --null %PTM_playtime_{nick}:luminto%",
                    )
                ).replace("\n", "").strip() or "Менее минуты"
        except Exception:
            time_played = "Неизвестно"
    else:
        m_day = m_week = m_month = m_all = 0
        time_played = "-"

    balance = await db.get_money(user_id)
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


@func.new_command([r"/time", r"/время$", r"/мск$", r"/msk$"])
async def msktime(event: Message) -> Message:
    """Показывает текущее московское время."""
    return await event.reply(
        phrase.time.format(datetime.now().strftime("%H:%M:%S"))
    )


@func.new_command(
    [r"(/г )?(шахта|майнить|копать)$", r"/mine", r"/(шахта|майнить|копать)$"],
)
async def mine_start(event: Message) -> Message:
    """Запускает сессию майнинга (шахты)."""
    user_id = event.sender_id
    if not (
        await states_helper.if_player(user_id)
        or await states_helper.if_author(user_id)
    ):
        return await event.reply(phrase.mine.not_in_state)
    if not await db.ready_to_mine(user_id):
        return await event.reply(choice(phrase.mine.not_ready))
    if user_id in mining.sessions:
        return await event.reply(phrase.mine.already)

    initial = randint(1, config.cfg.Mining.InitialGems)
    mining.sessions[user_id] = {
        "gems": initial,
        "death_chance": config.cfg.Mining.BaseDeathChance,
        "step": 1,
    }
    asyncio.create_task(mining.cleanup_session(user_id))

    return await event.reply(
        phrase.mine.done.format(
            formatter.value_to_str(initial, phrase.currency)
        )
        + phrase.mine.q,
        buttons=[
            [Button.inline(phrase.mine.button_yes, f"mine.yes.{user_id}")],
            [Button.inline(phrase.mine.button_no, f"mine.no.{user_id}")],
        ],
    )


@func.new_command([r"/nick(.*)", r"/ник(.*)"])
async def check_nick(event: Message) -> Message:
    """Показывает привязанный Minecraft ник пользователя."""
    arg = event.pattern_match.group(1).strip()
    user_id = None
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
        if (author_nick := await nicks.get_byid(event.sender_id)) is None:
            return await event.reply(phrase.nick.who)
        return await event.reply(phrase.nick.urnick.format(author_nick))

    nick = await nicks.get_byid(user_id)
    return await event.reply(
        phrase.nick.no_nick
        if nick is None
        else phrase.nick.usernick.format(nick),
    )


@func.new_command(
    [
        r"/скинуть(.*)",
        r"/кинуть(.*)",
        r"/дать(.*)",
        r"/перевести(.*)",
        r"перевести(.*)",
    ],
)
async def swap_money(event: Message) -> Message:
    """Переводит валюту другому игроку."""
    args = event.pattern_match.group(1).strip().split()
    if not args:
        return await event.reply(
            phrase.money.no_count + phrase.money.swap_balance_use
        )

    sender_id = event.sender_id
    try:
        recipient_id = await func.swap_resolve_recipient(event, args)
    except ValueError, TypeError, tgerrors.rpcerrorlist.UsernameInvalidError:
        return await event.reply(
            phrase.money.no_such_people + phrase.money.swap_balance_use
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
        amount = await db.get_money(sender_id)
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


@func.new_command(
    [
        r"/вывести (.+)",
        r"/вывод (.+)",
        r"/вмайн (.+)",
        r"/в майн (.+)",
        r"/вмаин (.+)",
        r"/в маин (.+)",
        r"вывести (.+)",
    ],
)
async def money_to_server(event: Message) -> Message:
    user_id = event.sender_id
    nick = await nicks.get_byid(user_id)
    if nick is None:
        return await event.reply(phrase.nick.not_append)

    try:
        amount = int(event.pattern_match.group(1).strip())
    except ValueError:
        return await event.reply(phrase.money.nan_count)

    if amount < 1:
        return await event.reply(phrase.money.negative_count)
    if amount > 64:
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


@func.new_command(
    [
        r"/вывести$",
        r"/вывод$",
        r"/вмайн$",
        r"/в майн$",
        r"/вмаин$",
        r"/в маин$",
        r"вывести$",
    ],
)
async def money_to_server_empty(event: Message) -> Message:
    return await event.reply(phrase.money.no_count)


@func.new_command(
    [
        r"/аметисты$",
        r"/баланс$",
        r"баланс$",
        r"/wallet",
        r"wallet$",
        r"/мой баланс$",
        r"мой баланс$",
    ],
)
async def get_balance(event: Message) -> Message:
    """Показывает баланс аметистов игрока."""
    return await event.reply(
        phrase.money.wallet.format(
            formatter.value_to_str(
                await db.get_money(event.sender_id), phrase.currency
            ),
        ),
    )


@func.new_command(
    [
        r"/linknick (.+)",
        r"/привязать (.+)",
        r"привязать (.+)",
        r"/новый ник (.+)",
        r"/линкник (.+)",
    ],
)
async def link_nick(event: Message) -> Message:
    nick = event.pattern_match.group(1).strip()
    if formatter.is_valid_mc_nick(nick) is False:
        return await event.reply(phrase.nick.invalid)

    current_linked_nick = await nicks.get_byid(event.sender_id)
    if current_linked_nick == nick:
        return await event.reply(phrase.nick.already_you)
    if await nicks.get_byname(nick) is not None:
        return await event.reply(phrase.nick.taken)

    if current_linked_nick is not None:
        return await event.reply(
            phrase.nick.already_have.format(
                price=formatter.value_to_str(
                    config.cfg.PriceForChangeNick, phrase.currency
                ),
            ),
            buttons=[
                [
                    Button.inline(
                        "✅ Сменить", f"nick.{nick}.{event.sender_id}".encode()
                    )
                ]
            ],
        )

    try:
        async with mcrcon.Vanilla as rcon:
            await rcon.send(f"nwl add name {nick}")
    except Exception:
        logger.error("RCON: Ошибка при добавлении в белый список")
        return await event.reply(phrase.nick.error)

    await db.add_money(event.sender_id, config.cfg.LinkGift)
    await nicks.link(event.sender_id, nick)

    ref_msg = None
    if (referral := await referrals.is_ref(event.sender_id)) is not None:
        await db.add_money(referral, config.cfg.RefGift)
        await db.add_money(event.sender_id, config.cfg.RefGift)
        ref_msg = phrase.ref.gift.format(config.cfg.RefGift)
        with contextlib.suppress(Exception):
            await client.send_message(
                referral,
                phrase.ref.used.format(
                    user=await func.get_name(event.sender_id, minecraft=True),
                    amount=config.cfg.RefGift,
                ),
            )

    logger.success(f"Юзер {event.sender_id} привязал свой ник!")
    await event.reply(
        phrase.nick.success.format(
            formatter.value_to_str(config.cfg.LinkGift, phrase.currency),
        ),
    )
    if ref_msg:
        await event.reply(ref_msg)

    try:
        return await aio.approve_chat_join_request(
            chat_id=config.chats.chat,
            user_id=event.sender_id,
        )
    except Exception:
        logger.info(
            f"Игрок {event.sender_id} привязал ник, но заявки нет. Пропускаю...",
        )


@func.new_command(
    [r"/linknick$", r"/привязать$", r"привязать$", r"/новый ник$", r"/линкник$"]
)
async def link_nick_empty(event: Message) -> Message:
    return await event.reply(phrase.nick.not_select)


@func.new_command([r"/серв$", r"/сервер", r"/server"])
async def sysinfo(event: Message) -> Message:
    """Выводит системную информацию о хосте бота."""
    return await event.reply(await sys.get_info())


@func.new_command([r"/randompic", r"/рандомпик$", r"/картинка$"])
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


@func.new_command([r"/map", r"/мап$", r"/карта$"])
async def getmap(event: Message) -> Message:
    """Выводит ссылку на онлайн-карту сервера."""
    return await event.reply(phrase.get_map, link_preview=False)


@func.new_command(
    [
        r"/vote@luminto_chatbot$",
        r"/vote$",
        r"/голос$",
        r"/голосование$",
        r"/проголосовать$",
    ],
)
async def vote(event: Message) -> Message:
    """Выводит ссылку на мониторинги для голосования."""
    return await client.send_message(
        event.chat_id,
        message=phrase.vote,
        reply_to=event.id,
        link_preview=False,
    )


@func.new_command(
    [
        r"/нпоиск (.+)",
        r"/пник (.+)",
        r"/игрок (.+)",
        r"/поискпонику (.+)",
        r"игрок (.+)",
        r"нпоиск (.+)",
        r"пник (.+)",
    ],
)
async def check_info_by_nick(event: Message) -> Message:
    """Ищет Telegram-профиль и статус игрока по его Minecraft нику."""
    nick = event.pattern_match.group(1).strip()
    user_id = await nicks.get_byname(nick)
    if user_id is None:
        return await event.reply(phrase.nick.not_find)

    state = await states_helper.if_player(
        user_id
    ) or await states_helper.if_author(user_id)
    return await event.reply(
        phrase.nick.info.format(
            tg=await func.get_name(user_id),
            role=phrase.roles.types[await roles.get_role(nick)],
            state=state or "Нет",
        ),
    )


@func.new_command(
    [
        r"/нпоиск$",
        r"/пник$",
        r"/игрок$",
        r"/поискпонику$",
        r"игрок$",
        r"нпоиск$",
        r"пник$",
    ],
)
async def check_info_by_nick_empty(event: Message) -> Message:
    return await event.reply(phrase.nick.empty)


@func.new_command(r"\+город (.+)")
async def cities_request(event: Message) -> Message:
    """Отправляет запрос администратору на добавление нового города."""
    word = event.pattern_match.group(1).strip().lower()
    async with aiofiles.open(pathes.chk_city) as aiof:
        if word in (await aiof.read()).splitlines():
            return await event.reply(phrase.cities.exists)
    async with aiofiles.open(pathes.bl_city) as aiof:
        if word in (await aiof.read()).splitlines():
            return await event.reply(phrase.cities.in_blacklist)

    user_name = await func.get_name(event.sender_id)
    try:
        await client.send_message(
            config.tokens.bot.creator,
            phrase.cities.request.format(user=user_name, word=word),
            buttons=[
                [
                    Button.inline(
                        "✅ Добавить",
                        f"cityadd.yes.{word}.{event.sender_id}".encode(),
                    ),
                    Button.inline(
                        "❌ Отклонить",
                        f"cityadd.no.{word}.{event.sender_id}".encode(),
                    ),
                ]
            ],
        )
    except tgerrors.ButtonDataInvalidError:
        return await event.reply(phrase.cities.long)
    return await event.reply(phrase.cities.set.format(word=word))


@func.new_command(r"\+города\s([\s\S]+)")
async def cities_requests(event: Message) -> Message:
    """Массовая проверка и отправка запросов на добавление городов."""
    words = [
        w.strip().lower()
        for w in event.pattern_match.group(1).splitlines()
        if w.strip()
    ]
    if not words:
        return await event.reply(phrase.cities.empty_long)

    status_msg = await event.reply(phrase.cities.checker)
    existing = set((await files.load_text_async(pathes.chk_city)).splitlines())
    blacklisted = set(
        (await files.load_text_async(pathes.bl_city)).splitlines()
    )

    output, pending = [], []
    for word in words:
        if word in existing:
            output.append(f"Город **{word}** - есть")
        elif word in blacklisted:
            output.append(f"Город **{word}** - в ЧС")
        else:
            pending.append(word)
            output.append(f"Город **{word}** - проверяется")
        if len(output) % 5 == 0:
            await status_msg.edit("\n".join(output))
            await asyncio.sleep(0.5)

    await status_msg.edit("\n".join(output))

    user_name = await func.get_name(event.sender_id)
    for word in pending:
        try:
            await client.send_message(
                config.tokens.bot.creator,
                phrase.cities.request.format(user=user_name, word=word),
                buttons=[
                    [
                        Button.inline(
                            "✅ Добавить",
                            f"cityadd.yes.{word}.{event.sender_id}".encode(),
                        ),
                        Button.inline(
                            "❌ Отклонить",
                            f"cityadd.no.{word}.{event.sender_id}".encode(),
                        ),
                    ]
                ],
            )
            await asyncio.sleep(0.3)
        except Exception:
            pass
    return None


@func.new_command(r"\-город (.+)")
async def cities_remove(event: Message) -> Message:
    """Удаляет город из базы (доступно администраторам)."""
    if await roles.get_user_role(event.sender_id) < roles.ADMIN:
        return await event.reply(
            phrase.roles.no_perms.format(
                level=roles.ADMIN, name=phrase.roles.admin
            ),
        )

    word = event.pattern_match.group(1).strip().lower()
    lines = (await files.load_text_async(pathes.chk_city)).splitlines()
    if word not in lines:
        return await event.reply(phrase.cities.not_exists)

    lines.remove(word)
    await files.save_text_async(pathes.chk_city, "\n".join(lines))
    return await event.reply(phrase.cities.deleted.format(word))


@func.new_command(
    [
        r"/rules",
        r"/правила$",
        r"/правилачата$",
        r"/правила сервера$",
        r"rules",
        r"правила$",
    ],
)
async def rules(event: Message) -> Message:
    """Выводит правила сервера/чата."""
    return await event.reply(phrase.rules.base, link_preview=False)


@func.new_command([r"онлайн$", r"/онлайн$", r"online$", r"/online"])
async def online(event: Message) -> Message:
    """Запрашивает список игроков онлайн через RCON."""
    try:
        async with mcrcon.Vanilla as rcon:
            response = await rcon.send("list")
        players_raw = (
            response.split(":", 1)[1].strip() if ":" in response else ""
        )
        players = [p.strip() for p in players_raw.split(",") if p.strip()]
        return await event.reply(
            phrase.online.format(list=", ".join(players), count=len(players)),
        )
    except Exception as e:
        logger.error(f"RCON Error during online list: {e}")
        return await event.reply(
            "❌ Не удалось получить список игроков (сервер недоступен).",
        )


@func.new_command([r"/newhint", r"/addhint"])
async def add_new_hint(event: Message) -> Message:
    """Запускает диалог для добавления новой подсказки к слову в игре Крокодил."""
    if not event.is_private:
        return await event.reply(phrase.newhints.private)

    word = await db.get_crocodile_word()
    async with client.conversation(event.sender_id, timeout=300) as conv:
        await conv.send_message(phrase.newhints.ask_hint.format(word=word))
        try:
            while True:
                response: Message = await conv.get_response()
                text = response.raw_text.strip()
                if text.lower() == "/стоп":
                    return await conv.send_message(phrase.newhints.cancel)
                if text.startswith("/"):
                    continue

                hint_cap = text.capitalize()
                pending_id = await db.add_pending_hint(
                    event.sender_id, hint_cap, word
                )
                await client.send_message(
                    config.tokens.bot.creator,
                    phrase.newhints.admin_alert.format(
                        word=word,
                        hint=hint_cap,
                        user=await func.get_name(event.sender_id),
                    ),
                    buttons=[
                        [
                            Button.inline("✅", f"hint.accept.{pending_id}"),
                            Button.inline("❌", f"hint.reject.{pending_id}"),
                        ]
                    ],
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

    if await roles.get_user_role(event.sender_id) < roles.ADMIN:
        return await event.reply(
            phrase.roles.no_perms.format(
                level=roles.ADMIN, name=phrase.roles.admin
            ),
        )

    hint: dict[str, Any] = await db.get_latest_pending_hint()
    if not hint:
        return await event.reply(phrase.newhints.not_found)

    return await event.reply(
        phrase.newhints.admin_alert.format(
            word=hint["word"],
            hint=hint["hint"],
            user=await func.get_name(hint["user"]),
        ),
        buttons=[
            [
                Button.inline("✅", f"hint.accept.{hint['id']}"),
                Button.inline("❌", f"hint.reject.{hint['id']}"),
            ]
        ],
    )


@func.new_command(r"/minimessage (.+)")
async def miniparser(event: Message) -> Message:
    text = event.pattern_match.group(1)
    out_path = pathes.mini_pic / f"{event.sender_id}.png"
    if minimessage.render(text, out_path=out_path) is False:
        return await event.reply(phrase.minimessage.too_long)

    try:
        return await client.send_file(
            entity=event.chat_id,
            file=out_path,
            reply_to=event.id,
            caption=phrase.minimessage.done,
        )
    finally:
        await anyio.Path(out_path).unlink(missing_ok=True)


@func.new_command(r"/сайт (.+)")
async def check_host(event: Message) -> Message:
    domain = func.extract_domain(event.pattern_match.group(1))
    if not domain:
        return await event.reply(phrase.check_host.invalid_url)

    data = await aiohost.check("http", domain)
    text = [phrase.check_host.checking.format(domain=domain)]
    for node, r in data["result"].items():
        res = r[0]
        text.append(
            f"{func.cc_to_flag(data['info']['nodes'][node][0])} : {node} - "
            + (
                f"✅ - Пинг {round(res[1] * 1000)} мс"
                if res[0] == 1
                else f"❌ - {res[2]}"
            ),
        )
    return await event.reply("\n".join(text))


@func.new_command(r"/test", min_role=4)
async def test(event: Message) -> Message:
    return await event.reply(str(await roles.api.get_all_roles()))
