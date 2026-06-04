import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from .. import db, phrase
from . import func
from .client import client

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


async def send_to_subscribers(message_text):
    """Отправка сообщения всем подписчикам."""
    data = db.mailing_get()
    subscribers = data.get("subscribers", [])

    if not subscribers:
        return 0

    successful_sends = 0
    for user_id in subscribers:
        try:
            await client.send_message(
                user_id,
                f"{phrase.mailing.new}\n\n💬 : {message_text}\n\n__{phrase.mailing.upd_hint}__",
            )
            successful_sends += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.info(f"Ошибка отправки пользователю {user_id}: {e}")

    return successful_sends


@func.new_command(r"\+обновление ([\s\S]+)", min_role=4)
async def admin_broadcast(event: Message):
    await event.reply(
        phrase.mailing.done.format(
            await send_to_subscribers(event.pattern_match.group(1).strip()),
        ),
    )


@func.new_command(r"\+обновления")
async def subscribe_command(event: Message):
    """Обработчик команды подписки."""
    data = db.mailing_get()
    subscribers = data.get("subscribers", [])

    if event.sender_id in subscribers:
        return await event.reply(phrase.mailing.already_subscribe)
    subscribers.append(event.sender_id)
    data["subscribers"] = subscribers
    db.mailing_save(data)
    return await event.reply(phrase.mailing.subscribe)


@func.new_command(r"/отписаться$")
async def unsubscribe_command(event: Message):
    """Обработчик команды отписки."""
    data = db.mailing_get()
    subscribers = data.get("subscribers", [])

    if event.sender_id not in subscribers:
        return await event.reply(phrase.mailing.already_unsub)
    subscribers.remove(event.sender_id)
    data["subscribers"] = subscribers
    db.mailing_save(data)
    return await event.reply(phrase.mailing.unsub)
