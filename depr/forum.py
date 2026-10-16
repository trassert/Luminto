class forum:
    done_id = 5237699328843200968
    already_closed = "❌ : Тема уже закрыта!"
    closed = "✅ : **Тема закрыта.**\nПричина: {reason}"
    not_author = (
        "⚠️ : Только автор темы и администратор может использовать эту команду."
    )
    topic_no_id = "⚠️ : Не могу получить ID темы."
    topic_no_name = "⚠️ : Укажите название темы: `+топик Название`"
    topic_created = "✅ : Тема создана: **[{title}]({link})**"



async def rm_closed_topics() -> None:
    try:
        data = await files.load_json_async(pathes.rmtopics)
    except Exception:
        return None
    ttl_seconds = config.cfg.ClosedTopicsTTL * 24 * 60 * 60
    changed = False
    for topic_id in list(data.keys()):
        if time.time() - data[topic_id] <= ttl_seconds:
            continue
        try:
            await client(
                functions.messages.DeleteTopicHistoryRequest(
                    peer=config.chats.forum,
                    top_msg_id=int(topic_id),
                ),
            )
        except Exception as e:
            logger.warning(f"Ошибка при удалении топика {topic_id}: {e}")
        data.pop(topic_id, None)
        changed = True
    if changed:
        return await files.save_json_async(pathes.rmtopics, data)
    return None


import time
from typing import TYPE_CHECKING

from loguru import logger
from telethon.errors.rpcbaseerrors import BadRequestError
from telethon.tl import functions

from .. import config, db, files, pathes, phrase, roles
from . import func
from .client import client

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


async def addwait_rm_topic(topic_id: int):
    try:
        data = await files.load_json_async(pathes.rmtopics)
    except Exception:
        data = {}
    data[str(topic_id)] = time.time()
    await files.save_json_async(pathes.rmtopics, data)


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
        await event.reply(
            phrase.forum.topic_created.format(link=link, title=title),
        )
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
        str(topic_id) not in author_topics
        and await roles.get_user_role(event.sender_id) < roles.ADMIN
    ):
        return await event.reply(phrase.forum.not_author)
    try:
        await client(
            functions.messages.EditForumTopicRequest(
                peer=config.chats.forum,
                topic_id=topic_id,
                icon_emoji_id=phrase.forum.done_id,
            ),
        )
        await client(
            functions.messages.EditForumTopicRequest(
                peer=config.chats.forum,
                topic_id=topic_id,
                closed=True,
            ),
        )
    except BadRequestError as e:
        logger.error(f"Ошибка закрытия топика: {e}")
        return await event.reply(phrase.forum.already_closed)
    await addwait_rm_topic(topic_id)
    return await event.reply(
        phrase.forum.closed.format(reason=reason or "Без причины"),
    )




class Topics:
    def __init__(self):
        self.data_file = pathes.topics
        if not self.data_file.exists():
            files.save_json_sync(self.data_file, {})

    def idconv(self, id):
        try:
            return str(id)
        except Exception as e:
            msg = f"Невозможно конвертировать ID {id} в строку"
            raise ValueError(msg) from e

    async def get_byid(self, id: str) -> dict:
        id = self.idconv(id)
        self.data = await files.load_json_async(self.data_file)
        return self.data.get(id, [])

    async def add(self, id: str, topic_id: str) -> None:
        id = self.idconv(id)
        topic_id = self.idconv(topic_id)
        self.data = await files.load_json_async(self.data_file)
        if id not in self.data:
            self.data[id] = []
        self.data[id].append(topic_id)
        return await files.save_json_async(
            self.data_file,
            self.data,
            indent=True,
        )

    async def remove(self, id: str, topic_id: str) -> bool:
        id = self.idconv(id)
        topic_id = self.idconv(topic_id)
        self.data = await files.load_json_async(self.data_file)
        if topic_id in self.data.get(id, []):
            self.data[id].remove(topic_id)
            await files.save_json_async(self.data_file, self.data, indent=True)
            return True
        return False

topics = Path("db") / "users" / "topics.json"

rmtopics = Path("db") / "timings" / "rmtopics.json"