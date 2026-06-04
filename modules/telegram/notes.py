from typing import TYPE_CHECKING

from loguru import logger

from .. import db, phrase
from . import func
from .client import client

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


@func.new_command([r"\+note (.+)\n([\s\S]+)",r"\+нот (.+)\n([\s\S]+)"], min_role=1)
async def add_note(event: Message):
    if (
        db.Notes().create(
            event.pattern_match.group(1).strip(),
            event.text.split("\n", maxsplit=1)[1],
        )
        is True
    ):
        return await event.reply(
            phrase.notes.new.format(event.pattern_match.group(1).strip()),
        )
    return await event.reply(phrase.notes.already_added)


@func.new_command([r"\+note (.+)$",r"\+нот (.+)$"], min_role=1)
async def add_note_notext(event: Message):
    return await event.reply(phrase.notes.notext)


@func.new_command([r"\+нот\n([\s\S]+)",r"\+note\n([\s\S]+)"], min_role=1)
async def add_note_noname(event: Message):
    return await event.reply(phrase.notes.noname)


@func.new_command(r"\.(.+)")
async def get_note(event: Message):
    note_text = db.Notes().get(event.pattern_match.group(1).strip().lower())
    if note_text is None:
        return None
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


@func.new_command(r"/notes$")
@func.new_command(r"/ноты$")
async def get_all_notes(event: Message):
    text = ""
    n = 1
    for name in db.Notes().get_all():
        text += f"{n}. {name}\n"
        n += 1
    return await event.reply(phrase.notes.alltext.format(text))


@func.new_command([r"\-нот (.+)$", r"\-note (.+)$", r"\-text (.+)$"], min_role=1)
async def del_note(event: Message):
    if not db.Notes().remove(event.pattern_match.group(1).strip()):
        return await event.reply(phrase.notes.not_found)
    return await event.reply(phrase.notes.deleted)


@func.new_command([r"\-text$", r"\-нот$", r"\-note$"], min_role=1)
async def del_note_notext(event: Message):
    return await event.reply(phrase.note.noname)
