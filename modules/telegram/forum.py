from typing import TYPE_CHECKING

from loguru import logger
from telethon.tl import functions

from .. import config, phrase
from . import func
from .client import client

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


@func.new_command(r"\+топик (.+)", chats=config.chats.forum)
async def create_topic(event: Message):
    title: str = event.pattern_match.group(1).strip()
    if not title:
        return await event.reply(phrase.forum.topic_no_name)

    title = title.capitalize()
    try:
        result = await client(
            functions.messages.CreateForumTopicRequest(
                peer=config.chats.forum,
                title=title,
            ),
        )
        topic_id = result.updates[0].id
        link = f"https://t.me/c/{str(config.chats.forum)[4:]}/{topic_id}"
        await event.reply(phrase.forum.topic_created.format(link=link, title=title))
    except Exception:
        logger.exception("Ошибка создания топика")


@func.new_command(r"\-топик", chats=config.chats.forum)
async def delete_topic(event: Message):
    event.reply(f"event.reply_to_msg_id {event.reply_to_msg_id}")
    event.reply(
        f"getattr(event.reply_to, 'reply_to_top_id', None) {getattr(event.reply_to, 'reply_to_top_id', None)}"
    )
