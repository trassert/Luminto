import asyncio
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
            phrase.ai.wait_until.format(fw_request)
        )
        await asyncio.sleep(fw_request)
    try:
        user = await client.get_entity(event.sender_id)
        full_name = (
            f"{(user.first_name or '')} {(user.last_name or '')}".strip()
        )
    except Exception:
        full_name = "Неопознанный персонаж"
    text = ""
    last_edit_len = 0
    async for chunk in ai.Ai.generate_response(full_name, req):
        text += chunk
        if len(text) > 4000:
            message = await event.reply(text)
            last_edit_len = len(text)
            text = ""
            continue
        if not message:
            message = await event.reply(text)
            last_edit_len = len(text)
            continue
        if len(text) - last_edit_len >= 200:
            try:
                await message.edit(text)
                last_edit_len = len(text)
            except MessageNotModifiedError:
                pass
    if message and len(text) > last_edit_len:
        try:
            await message.edit(text)
        except MessageNotModifiedError:
            pass
    return None
