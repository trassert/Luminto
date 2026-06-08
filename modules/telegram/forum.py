from typing import TYPE_CHECKING

from loguru import logger
from telethon.tl import functions

from .. import config, db, phrase
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
        await db.Topics().add(event.sender_id, topic_id)
        await event.reply(phrase.forum.topic_created.format(link=link, title=title))
    except Exception:
        logger.exception("Ошибка создания топика")


@func.new_command(r"\-топик(.*)", chats=config.chats.forum)
async def delete_topic(event: Message):
    reason: str = event.pattern_match.group(1).strip()
    topic_id = event.reply_to_msg_id
    if not topic_id:
        return await event.reply(phrase.forum.topic_no_id)
    author_topics = await db.Topics().get_byid(event.sender_id)
    if (
        topic_id not in author_topics
        and await db.Roles().get(event.sender_id) < db.Roles.ADMIN
    ):
        return await event.reply(phrase.forum.not_author)
    result = await client(
        functions.messages.EditForumTopicRequest(
            peer=config.chats.forum, topic_id=topic_id, closed=True
        )
    )
    print(result)
    return await event.reply(phrase.forum.closed.format(reason=reason or "Без причины"))
