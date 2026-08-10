from typing import TYPE_CHECKING

from loguru import logger

from .. import db, formatter, phrase, tickets
from . import func

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


@func.new_command([r"\+чек(.*)", r"\+ticket(.*)"])
async def do_ticket(event: Message):
    if not event.is_private:
        return await event.reply(phrase.ticket.in_chat)
    arg = event.pattern_match.group(1).strip()
    if arg == "":
        return await event.reply(phrase.ticket.no_value)
    try:
        arg = int(arg)
    except ValueError:
        return await event.reply(phrase.ticket.not_int)
    if arg < 1:
        return await event.reply(phrase.ticket.bigger_than_zero)
    balance = await db.get_money(event.sender_id)
    if balance < arg:
        return await event.reply(
            phrase.money.not_enough.format(
                formatter.value_to_str(balance, phrase.currency),
            ),
        )
    await db.add_money(event.sender_id, -arg)
    ticket_id = await tickets.add(event.sender_id, arg)
    return await event.reply(
        phrase.ticket.added.format(
            value=arg,
            author=await func.get_name(event.sender_id),
            id=ticket_id,
        ),
    )


@func.new_command(
    [
        r"/чек(.*)",
        r"/ticket(.*)",
        r"/активировать(.*)",
        r"активировать(.*)",
        r"/activate(.*)",
    ]
)
async def get_ticket(event: Message):
    arg = event.pattern_match.group(1).strip()
    if arg == "":
        return await event.reply(phrase.ticket.no_value)
    ticket_info = await tickets.get(arg)
    if ticket_info is None:
        return await event.reply(phrase.ticket.no_such)
    await db.add_money(event.sender_id, ticket_info["value"])
    await tickets.delete(arg)
    return await event.reply(
        phrase.ticket.got.format(
            author=await func.get_name(ticket_info["author"]),
            value=formatter.value_to_str(ticket_info["value"], phrase.currency),
        ),
    )
