from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger
from telethon.tl.functions.users import GetFullUserRequest

from .. import db, formatter, mcrcon, pathes, phrase
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


@func.new_command([r"\+staff(.*)", r"\+стафф(.*)"], min_role=5)
async def add_staff(event: Message):
    arg = event.pattern_match.group(1).strip()
    try:
        user = await client(GetFullUserRequest(arg))
        user = user.full_user.id
        tag = await func.get_name(user)
    except IndexError, ValueError:
        reply_to_msg = event.reply_to_msg_id
        if reply_to_msg:
            reply_message = await event.get_reply_message()
            user = reply_message.sender_id
            tag = await func.get_name(user)
        else:
            return await event.reply(phrase.money.no_people)
    roles = db.Roles()
    new_role = await roles.get(user) + 1
    await roles.set(user, new_role)
    return await event.reply(
        phrase.perms.upgrade.format(nick=tag, staff=new_role),
    )


@func.new_command([r"\-staff(.*)", r"\-стафф(.*)"], min_role=5)
async def del_staff(event: Message):
    roles = db.Roles()
    arg = event.pattern_match.group(1).strip()
    try:
        user = await client(GetFullUserRequest(arg))
        user = user.full_user.id
        tag = await func.get_name(user)
    except IndexError, ValueError:
        reply_to_msg = event.reply_to_msg_id
        if reply_to_msg:
            reply_message = await event.get_reply_message()
            user = reply_message.sender_id
            tag = await func.get_name(user)
        else:
            return await event.reply(phrase.money.no_people)
    new_role = await roles.get(user) - 1
    await roles.set(user, new_role)
    return await event.reply(
        phrase.perms.downgrade.format(nick=tag, staff=new_role),
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
            phrase.money.no_count + phrase.money.give_money_use
        )

    try:
        count = int(args[0])
    except ValueError:
        return await event.reply(
            phrase.money.nan_count + phrase.money.give_money_use
        )

    if count <= 0:
        return await event.reply(phrase.money.negative_count)

    user = await func.swap_resolve_recipient(event, args)
    if user is None:
        return await event.reply(
            phrase.money.no_people + phrase.money.give_money_use
        )

    try:
        entity = await client.get_entity(user)
        if entity.bot:
            return await event.reply(phrase.money.bot)
    except Exception:
        return await event.reply(
            phrase.money.no_people + phrase.money.swap_balance_use
        )

    await db.add_money(user, count)
    return await event.reply(
        phrase.money.give_money.format(
            formatter.value_to_str(count, phrase.currency)
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
