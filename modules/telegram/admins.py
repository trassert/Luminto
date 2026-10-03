from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger
from telethon.tl.functions.users import GetFullUserRequest

from .. import db, formatter, mcrcon, nicks, pathes, phrase, roles
from . import func
from .client import client

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


@func.new_command([r"/change balance(.*)", r"/изменить баланс(.*)"], min_role=4)
async def add_balance(event: Message):
    args = event.pattern_match.group(1).strip().split()
    try:
        tag = args[1]
        user = await client(GetFullUserRequest(tag))
    except IndexError:
        return await event.reply(
            phrase.money.no_people + phrase.money.change_balance_use,
        )
    except ValueError:
        return await event.reply(
            phrase.money.no_such_people + phrase.money.change_balance_use,
        )
    try:
        new = int(args[0])
    except IndexError:
        return await event.reply(
            phrase.money.no_count + phrase.money.change_balance_use,
        )
    except ValueError:
        return await event.reply(
            phrase.money.nan_count + phrase.money.change_balance_use,
        )
    old = await db.get_money(user.full_user.id)
    await db.add_money(user.full_user.id, new)
    await event.reply(
        phrase.money.add_money.format(name=tag, old=old, new=old + new),
    )
    return None


@func.new_command([r"\+staff(.*)", r"\+стафф(.*)"], min_role=roles.OWNER)
async def add_staff(event: Message):
    arg = event.pattern_match.group(1).strip()
    try:
        user = (
            await func.get_id(arg)
            if arg
            else await func.get_author_by_msgid(
                event.chat_id,
                func.get_reply_message_id(event),
            )
        )
    except Exception:
        user = None
    if user is None:
        return await event.reply(phrase.money.no_people)
    tag = await func.get_name(user)
    nick = await nicks.get_byid(user)
    if not nick:
        return await event.reply(phrase.perms.no_minecraft)
    current_role = await roles.get_role(nick)
    if current_role == roles.OWNER:
        return await event.reply(phrase.perms.max_role)
    new_role = current_role + 1
    await roles.set_role(nick, new_role)
    return await event.reply(
        phrase.perms.upgrade.format(nick=tag, staff=new_role),
    )


@func.new_command([r"\-staff(.*)", r"\-стафф(.*)"], min_role=roles.OWNER)
async def del_staff(event: Message):
    arg = event.pattern_match.group(1).strip()
    try:
        user = (
            await func.get_id(arg)
            if arg
            else await func.get_author_by_msgid(
                event.chat_id,
                func.get_reply_message_id(event),
            )
        )
    except Exception:
        user = None
    if user is None:
        return await event.reply(phrase.money.no_people)
    tag = await func.get_name(user)
    nick = await nicks.get_byid(user)
    if not nick:
        return await event.reply(phrase.perms.no_minecraft)
    current_role = await roles.get_role(nick)
    if current_role == roles.DEFAULT:
        return await event.reply(phrase.perms.min_role)
    new_role = current_role - 1
    await roles.set_role(nick, new_role)
    return await event.reply(
        phrase.perms.downgrade.format(nick=tag, staff=new_role),
    )


@func.new_command(r"/чсб(.*)", min_role=roles.ADMIN)
async def add_bot_blacklist(event: Message):
    args = event.pattern_match.group(1).strip()
    reply_id = func.get_reply_message_id(event)
    if reply_id:
        user = await func.get_author_by_msgid(event.chat_id, reply_id)
        reason = args
    else:
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            return await event.reply(phrase.bot_blacklist.add_use)
        try:
            user = await func.get_id(parts[0])
        except Exception:
            return await event.reply(phrase.money.no_people)
        reason = parts[1]
    if user is None:
        return await event.reply(phrase.money.no_people)
    if not reason:
        return await event.reply(phrase.bot_blacklist.add_use)
    await roles.add_to_blacklist(user, reason)
    return await event.reply(
        phrase.bot_blacklist.added.format(user=await func.get_name(user)),
    )


@func.new_command(r"-чсб(.*)", min_role=roles.ADMIN)
async def remove_bot_blacklist(event: Message):
    arg = event.pattern_match.group(1).strip()
    reply_id = func.get_reply_message_id(event)
    if reply_id:
        user = await func.get_author_by_msgid(event.chat_id, reply_id)
    elif arg:
        try:
            user = await func.get_id(arg.split()[0])
        except Exception:
            return await event.reply(phrase.money.no_people)
    else:
        return await event.reply(phrase.bot_blacklist.remove_use)
    if user is None:
        return await event.reply(phrase.money.no_people)
    if not await roles.remove_from_blacklist(user):
        return await event.reply(phrase.bot_blacklist.not_found)
    return await event.reply(
        phrase.bot_blacklist.removed.format(user=await func.get_name(user)),
    )


@func.new_command(r"//(.+)", min_role=4)
async def vanilla_mcrcon(event: Message):
    command = event.pattern_match.group(1).strip()
    try:
        async with mcrcon.Vanilla as rcon:
            resp = formatter.rm_colors(await rcon.send(command))
            if len(resp) == 0:
                logger.info("Пустой ответ")
                return await event.reply(phrase.rcon.empty)
            logger.info(f"Ответ команды:\n{resp}")
            if len(resp) > 4096:
                for x in range(0, len(resp), 4096):
                    await event.reply(f"```{resp[x : x + 4096]}```")
                return None
            return await event.reply(f"```{resp}```")
    except TimeoutError:
        return await event.reply(phrase.server.stopped)


@func.new_command(
    [
        r"\+wl\s(.+)",
        r"\-wl\s(.+)",
        r"\-wl\s(.+)",
        r"\-вт\s(.+)",
    ],
    min_role=1,
)
async def whitelist(event: Message):
    if event.text[0] == "-":
        command = f"nwl remove name {event.pattern_match.group(1).strip()}"
    else:
        command = f"nwl add name {event.pattern_match.group(1).strip()}"
    logger.info(f"Выполняется команда: {command}")
    try:
        async with mcrcon.Vanilla as rcon:
            resp = formatter.rm_colors(await rcon.send(command)).strip()
            logger.info(f"Ответ команды:\n{resp}")
            return await event.reply(
                f"‼️ Команда скоро будет выведена!\n✍🏻 : {resp}",
            )
    except TimeoutError:
        return await event.reply(phrase.server.stopped)


@func.new_command(r"/выдать(.*)", min_role=4)
async def give_money(event: Message):
    args = event.pattern_match.group(1).strip().split()
    if not args:
        return await event.reply(
            phrase.money.no_count + phrase.money.give_money_use,
        )

    try:
        count = int(args[0])
    except ValueError:
        return await event.reply(
            phrase.money.nan_count + phrase.money.give_money_use,
        )

    if count <= 0:
        return await event.reply(phrase.money.negative_count)

    user = await func.swap_resolve_recipient(event, args)
    if user is None:
        return await event.reply(
            phrase.money.no_people + phrase.money.give_money_use,
        )

    try:
        entity = await client.get_entity(user)
        if entity.bot:
            return await event.reply(phrase.money.bot)
    except Exception:
        return await event.reply(
            phrase.money.no_people + phrase.money.swap_balance_use,
        )

    await db.add_money(user, count)
    return await event.reply(
        phrase.money.give_money.format(
            formatter.value_to_str(count, phrase.currency),
        ),
    )


@func.new_command(r"\+pic(.*)", min_role=4)
async def save_pic(event: Message):
    # Проверяем есть ли картинка в самом сообщении
    if event.photo:
        try:
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
            filepath = pathes.pic / filename
            await event.download_media(file=filepath)
            logger.info(f"Картинка сохранена: {filepath}")
            return await event.reply(phrase.pic.save)
        except Exception as e:
            logger.error(f"Ошибка при сохранении картинки: {e}")
            return await event.reply(phrase.pic.error)

    # Проверяем есть ли картинка в реплае
    reply_to_msg_id = func.get_reply_message_id(event)
    if reply_to_msg_id:
        try:
            reply_message = await event.get_reply_message()
            if reply_message.photo:
                filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
                filepath = pathes.pic / filename
                await reply_message.download_media(file=filepath)
                logger.info(f"Картинка сохранена из реплая: {filepath}")
                return await event.reply(phrase.pic.save)
        except Exception as e:
            logger.error(f"Ошибка при сохранении картинки из реплая: {e}")
            return await event.reply(phrase.pic.error)

    return await event.reply(phrase.pic.no_pic)
