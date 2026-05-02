import asyncio
from aiogram import Router, exceptions, types
from loguru import logger
from telethon import events
from telethon.errors import UserNotParticipantError

from .. import config, db, formatter, mcrcon, phrase
from . import func
from .client import client, dp

logger.info(f"Загружен модуль {__name__}!")

router = Router(name="actions")

# Задержка перед приветствием для фильтрации спам-ботов (сек)
WELCOME_DELAY = 5


@client.on(events.ChatAction(chats=config.chats.chat))
async def chat_action(event: events.ChatAction.Event):
    if not event.user_id:
        return

    try:
        user_name = await func.get_name(event.user_id)
    except TypeError:
        return None

    if event.user_left:
        nick = await db.Nicks(id=event.user_id).get()
        if nick is None:
            messages = "0"
            time_played = "0 секунд"
        else:
            try:
                async with mcrcon.Vanilla as rcon:
                    raw_time: str = await rcon.send(
                        f"papi parse --null %PTM_playtime_{nick}:luminto%",
                    )
                    time_played: str = raw_time.replace("\n", "").strip()
                    if time_played == "":
                        time_played = "Менее минуты"
                messages: int = await db.Statistic().get(nick, all_days=True)
            except Exception as e:
                logger.error(f"Ошибка при получении данных для {nick}: {e}")
                time_played = "0 секунд"
                messages = "0"
        return await client.send_message(
            config.chats.chat,
            phrase.chataction.leave.format(                nick=user_name, time=time_played, messages=messages
            ),
        )

    if event.user_joined or event.user_added:
        if formatter.check_zalgo(user_name) > 50:
            try:
                await client.edit_permissions(
                    config.chats.chat,
                    event.user_id,
                    send_messages=False,
                )
            except Exception:
                pass
            return await client.send_message(
                config.chats.chat,
                phrase.chataction.zalgo.format(user_name),
                silent=False,
            )

        if not db.hellomsg_check(event.user_id):
            return None

        await asyncio.sleep(WELCOME_DELAY)

        try:
            await client.get_participants(config.chats.chat, ids=event.user_id)
        except (UserNotParticipantError, ValueError):
            logger.info(f"Пользователь {event.user_id} удален до приветствия.")
            return None

        return await client.send_message(
            config.chats.chat,
            phrase.chataction.hello.format(user_name),
            link_preview=False,
        )

    return None


@router.chat_join_request()
async def handle_join_request(request: types.ChatJoinRequest):
    """Обработка запроса на вступление."""
    user_id = request.from_user.id

    if await db.Nicks(id=user_id).get() is not None:
        try:
            await request.approve()
        except exceptions.TelegramBadRequest:
            pass        return

    try:
        await request.bot.send_message(
            chat_id=user_id,
            text=phrase.chataction.need_link,
            parse_mode="HTML",
            link_preview_options=types.LinkPreviewOptions(is_disabled=True),
        )
    except exceptions.TelegramForbiddenError:
        logger.info(f"ЛС закрыты у пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки инструкции {user_id}: {e}")


dp.include_router(router)