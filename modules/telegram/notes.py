from typing import TYPE_CHECKING

from loguru import logger

from .. import db, notes, phrase
from . import func
from .client import client

if TYPE_CHECKING:
    from telethon.tl.custom import Message
logger.info(f"Загружен модуль {__name__}!")


@func.new_command(
    [r"\+note (.+)\n([\s\S]+)", r"\+нот (.+)\n([\s\S]+)"], min_role=1
)
async def add_note(event: Message):
    name = event.pattern_match.group(1).strip()
    if await notes.create(
        event.sender_id, name, event.text.split("\n", maxsplit=1)[1]
    ):
        return await event.reply(
            phrase.notes.new.format(name),
        )
    return await event.reply(phrase.notes.already_added)


@func.new_command([r"\+note (.+)$", r"\+нот (.+)$"], min_role=1)
async def add_note_notext(event: Message):
    return await event.reply(phrase.notes.notext)


@func.new_command([r"\+нот\n([\s\S]+)", r"\+note\n([\s\S]+)"], min_role=1)
async def add_note_noname(event: Message):
    return await event.reply(phrase.notes.noname)


@func.new_command(r"\.(.+)")
async def get_note(event: Message):
    note_data = await notes.get(event.pattern_match.group(1).strip().lower())
    if note_data is None:
        return None
    note_text = note_data["text"]
    if event.reply_to_msg_id:
        reply_message: Message = await event.get_reply_message()
        if reply_message is None:
            return None
        return await client.send_message(
            event.chat_id,
            note_text,
            reply_to=reply_message.id,
            link_preview=False,
        )
    return await client.send_message(
        event.chat_id,
        note_text,
        reply_to=event.id,
        link_preview=False,
    )


@func.new_command([r"/notes$", r"/ноты$"])
async def get_all_notes(event: Message):
    allnotes = notes.get_all()
    if allnotes == []:
        return await event.reply(phrase.notes.empty)
    text = ""
    n = 1
    for name in allnotes:
        text += f"{n}. {name}\n"
        n += 1
    return await event.reply(phrase.notes.alltext.format(text))


@func.new_command([r"/моиноты$", r"/mynotes$"], min_role=1)
async def get_my_notes(event: Message):
    info = await notes.get_by_author(event.sender_id)
    if info == []:
        return await event.reply(phrase.notes.my_notes_empty)
    text = ""
    n = 1
    for name in info:
        text += f"{n}. {name}\n"
        n += 1
    return await event.reply(phrase.notes.my_notes.format(text))


@func.new_command(
    [r"\-нот (.+)$", r"\-note (.+)$", r"\-text (.+)$"], min_role=1
)
async def del_note(event: Message):
    name = event.pattern_match.group(1).strip()
    note_data = await notes.get(name)
    if note_data is None:
        return await event.reply(phrase.notes.not_found)
    if (
        event.sender_id != note_data["author"]
        and not await db.Roles().get(event.sender_id) >= 4
    ):
        return await event.reply(phrase.notes.not_author)
    if not await notes.remove(name):
        return await event.reply(phrase.notes.not_found)
    return await event.reply(phrase.notes.deleted)


@func.new_command([r"\-text$", r"\-нот$", r"\-note$"], min_role=1)
async def del_note_notext(event: Message):
    return await event.reply(phrase.note.noname)
