import re
from typing import TYPE_CHECKING

from loguru import logger
from telethon import events
from telethon.tl.functions.users import GetFullUserRequest

from .. import db, nicks, phrase
from .client import client

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


async def get_simple_push(id) -> str | None:
    try:
        user = await client.get_entity(id)
    except Exception:
        return None
    if user.username:
        return user.username
    return None


async def get_name(id, push=False, minecraft=False, log=False) -> str | None:
    """Возвращает имя пользователя в формате: имя+фамилия, @username или Minecraft-ник."""

    id = int(id)

    if minecraft:
        nick = await nicks.get_byid(id)
        return f"[{nick}](tg://user?id={id})" if nick else None

    try:
        user = await client.get_entity(id)
    except Exception:
        return "Неопознанный персонаж"

    first = (user.first_name or "").replace("[", "(").replace("]", ")")
    last = (user.last_name or "").replace("[", "(").replace("]", ")")
    full_name = f"{first} {last}".strip()

    if log:
        return f"@{id} ({full_name or 'Без имени'})"

    if push and user.username:
        return f"@{user.username}"

    display = full_name or first or "Без имени"
    return f"[{display}](tg://user?id={id})"


async def get_id(str: str) -> int:
    if str[-1] == ",":
        str = str[:-1]
    if bool(re.fullmatch(r"@\d+", str)):
        str = str[1:]
        check = await get_name(str)
        if check in ["Без имени", "Неопознанный персонаж"]:
            msg = "Пользователь с таким ID не найден."
            logger.warning(msg + f" ID: {str}")
            raise ValueError(msg)
        return int(str)
    user = await client(GetFullUserRequest(str))
    return user.full_user.id


def get_reply_message_id(event):
    if event.reply_to is None:
        return None
    if not event.reply_to.forum_topic:
        return event.reply_to.reply_to_msg_id
    if event.reply_to.reply_to_top_id is None:
        return None
    return event.reply_to.reply_to_msg_id


async def get_author_by_msgid(chat_id: int, msg_id: int) -> int | None:
    if not msg_id or msg_id <= 0:
        return None
    msg = await client.get_messages(chat_id, ids=msg_id)
    return msg.sender_id if msg else None


async def swap_resolve_recipient(event: Message, args: list[str]) -> int | None:
    """Возвращает ID получателя или None."""
    if len(args) > 1:
        try:
            return await get_id(args[1])
        except Exception:
            pass
    msg_id = get_reply_message_id(event)
    if msg_id:
        return await get_author_by_msgid(event.chat_id, msg_id)
    return None


async def checks(
    event: Message | events.CallbackQuery.Event, min_role: int = 0
) -> bool:
    "Логгирование ЛС"
    if event.is_private and not isinstance(event, events.CallbackQuery.Event):
        name = await get_name(event.sender_id, log=True)
        (
            logger.info(f"ЛС - {name} > {event.text}")
            if len(event.text) < 100
            else logger.info(f"ЛС - {name} > {event.text[:100]}...")
        )

    "Логгирование кнопок"
    if isinstance(event, events.CallbackQuery.Event):
        name = await get_name(event.sender_id, log=True)
        logger.info(f"Кнопка - {name} > {event.data.decode('utf-8')}")

    "Проверка на ЧСБ и ур. доступа"
    roles = db.Roles()
    u_role = await roles.get(event.sender_id)
    if u_role == roles.BLACKLIST:
        if isinstance(event, events.CallbackQuery.Event):
            await event.answer(phrase.blacklisted, alert=True)
        else:
            await event.reply(phrase.blacklisted)
        return False
    if u_role < min_role:
        if isinstance(event, events.CallbackQuery.Event):
            await event.answer(
                phrase.roles.no_perms_buttons.format(
                    name=phrase.roles.types[min_role]
                ),
                alert=True,
            )
        else:
            await event.reply(
                phrase.roles.no_perms.format(
                    level=min_role, name=phrase.roles.types[min_role]
                )
            )
        return False
    return True


def new_command(
    command: str | list[str], checks=checks, chats=None, min_role: int = 0
):
    async def check_wrapper(event):
        return await checks(event, min_role=min_role)

    if isinstance(command, str):

        def decorator(func):
            client.add_event_handler(
                func,
                events.NewMessage(
                    pattern=rf"(?i)^{command}", func=check_wrapper, chats=chats
                ),
            )
            return func

        return decorator

    if isinstance(command, list):

        def decorator(func):
            for pattern in command:
                client.add_event_handler(
                    func,
                    events.NewMessage(
                        pattern=rf"(?i)^{pattern}",
                        func=check_wrapper,
                        chats=chats,
                    ),
                )
            return func

        return decorator
    msg = "Expected str | list[str], got " + type(command).__name__
    raise ValueError(msg)


def new_callback(pattern: str, checks=checks, min_role: int = 0):
    async def check_wrapper(event):
        return await checks(event, min_role=min_role)

    def decorator(func):
        client.add_event_handler(
            func,
            events.CallbackQuery(pattern=rf"^{pattern}", func=check_wrapper),
        )
        return func

    return decorator
