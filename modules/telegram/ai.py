import asyncio
import contextlib
from typing import TYPE_CHECKING

from loguru import logger
from telethon.errors.rpcerrorlist import MessageNotModifiedError

from .. import ai, config, floodwait, phrase
from . import func
from .client import client

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


@func.new_command([r"/ai ([\s\S]+)", r"/ии ([\s\S]+)"], min_role=1)
async def ai_handler(event: Message):
    if event.chat_id != config.chats.chat:
        return await event.reply(phrase.ai.not_in_chat)
    fw_request = floodwait.WaitAI.request()
    if fw_request is False:
        return await event.reply(phrase.wait.ai)
    req = event.pattern_match.group(1).strip()
    if fw_request == 0:
        message: Message = await event.reply(phrase.ai.wait)
    else:
        message: Message = await event.reply(
            phrase.ai.wait_until.format(fw_request),
        )
        await asyncio.sleep(fw_request)
    try:
        user = await client.get_entity(event.sender_id)
        full_name = (
            f"{(user.first_name or '')} {(user.last_name or '')}".strip()
        )
    except Exception:
        full_name = "Неопознанный персонаж"
    full_text = ""
    last_edit_len = 0
    async for chunk in ai.Ai.generate_response(full_name, req):
        full_text += chunk
        if len(full_text) > 4000:
            with contextlib.suppress(MessageNotModifiedError):
                await message.edit(full_text[:4000])
            message = await event.reply(full_text[4000:])
            full_text = full_text[4000:]
            last_edit_len = len(full_text)
            continue
        if len(full_text) - last_edit_len >= 200:
            with contextlib.suppress(MessageNotModifiedError):
                await message.edit(full_text)
                last_edit_len = len(full_text)
    if message and len(full_text) > last_edit_len:
        with contextlib.suppress(MessageNotModifiedError):
            await message.edit(full_text)
    return None
