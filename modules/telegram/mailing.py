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
    """Отправка сообщения всем подписчикам. Генератор, возвращает статусы."""
    subscribers = db.mailing_get()

    if not subscribers:
        yield {"total": 0, "successful": 0, "error": 0, "finished": True}
        return

    total = len(subscribers)
    successful_sends = 0
    error_sends = 0
    
    for i, user_id in enumerate(subscribers, 1):
        try:
            await client.send_message(
                user_id,
                f"💬 : {message_text}\n\n__{phrase.mailing.upd_hint}__",
            )
            successful_sends += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            error_sends += 1
            logger.info(f"Ошибка отправки пользователю {user_id}: {e}")
        if i % 10 == 0 or i == total:
            yield {
                "successful": successful_sends,
                "total": total,
                "error": error_sends,
                "finished": i == total
            }


@func.new_command(r"\+обновление ([\s\S]+)", min_role=4)
async def admin_broadcast(event: Message):
    status_msg = await event.reply(phrase.mailing.wait)
    async for data in send_to_subscribers(event.pattern_match.group(1).strip()):
        if not data["finished"]:
            await status_msg.edit(
                phrase.mailing.process.format(
                    current=data['successful'],
                    total=data['total'],
                    errors=data['error']
                )
            )
        else:
            await status_msg.edit(
                phrase.mailing.done.format(
                    count=data["total"],
                    error=data["error"]
                )
            )


@func.new_command(r"\+обновления")
async def subscribe_command(event: Message):
    """Обработчик команды подписки."""
    if db.mailing_addsub(event.sender_id):
        return await event.reply(phrase.mailing.subscribe)
    return await event.reply(phrase.mailing.already_subscribe)


@func.new_command(r"/отписаться$")
async def unsubscribe_command(event: Message):
    """Обработчик команды отписки."""
    if db.mailing_rmsub(event.sender_id):
        return await event.reply(phrase.mailing.unsub)
    return await event.reply(phrase.mailing.already_unsub)
