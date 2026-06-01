import re
from typing import TYPE_CHECKING

from loguru import logger
from telethon import events
from telethon.errors import UserNotParticipantError
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.functions.users import GetFullUserRequest

from .. import db, phrase
from .client import client

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


async def is_user_in_chat(chat, user_id: int) -> bool:
    try:
        await client(GetParticipantRequest(chat, user_id))
    except UserNotParticipantError, ValueError:
        return False
    else:
        return True


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
        nick = await db.Nicks(id=id).get()
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


# async def make_quiz_poll(
#     answers: list, correct_answer_id: int, question: str
# ) -> types.MessageMediaPoll:
#     return (
#         types.MessageMediaPoll(
#             poll=types.Poll(
#                 id=random.randint(1, 100000),
#                 question=types.TextWithEntities(
#                     text=question,
#                     entities=[],
#                 ),
#                 answers=[
#                     types.PollAnswer(
#                         text=types.TextWithEntities(text=option, entities=[]),
#                         option=bytes([i]),
#                     )
#                     for i, option in enumerate(answers, start=1)
#                 ],
#                 quiz=True,
#             ),
#             results=types.PollResults(
#                 results=[
#                     types.PollAnswerVoters(
#                         option=bytes([correct_answer_id]),
#                         voters=0,
#                         correct=True,
#                     ),
#                 ],
#             ),
#         ),
#     )
# Why i need ts? Probably unused


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


async def checks(event: Message | events.CallbackQuery.Event) -> bool:
    roles = db.Roles()
    if event.is_private and not isinstance(event, events.CallbackQuery.Event):
        name = await get_name(event.sender_id, log=True)
        (
            logger.info(f"ЛС - {name} > {event.text}")
            if len(event.text) < 100
            else logger.info(f"ЛС - {name} > {event.text[:100]}...")
        )
    if await roles.get(event.sender_id) != roles.BLACKLIST:
        return True
    if isinstance(event, events.CallbackQuery.Event):
        await event.answer(phrase.blacklisted, alert=True)
        return False
    await event.reply(phrase.blacklisted)
    return False


def new_command(command: str | list[str], checks=checks, chats=None):
    if isinstance(command, str):

        def decorator(func):
            client.add_event_handler(
                func,
                events.NewMessage(pattern=rf"(?i)^{command}", func=checks, chats=chats),
            )
            return func

        return decorator

    if isinstance(command, list):

        def decorator(func):
            for pattern in command:
                client.add_event_handler(
                    func,
                    events.NewMessage(
                        pattern=rf"(?i)^{pattern}", func=checks, chats=chats
                    ),
                )
            return func

        return decorator
    msg = "Expected str | list[str], got " + type(command).__name__
    raise ValueError(msg)
