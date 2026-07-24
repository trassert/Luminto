import re
from typing import TYPE_CHECKING

from loguru import logger

from .. import config, db, phrase
from . import func

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


@func.new_command(r"/addrefcode (.+)")
@func.new_command(r"/новыйреф (.+)")
@func.new_command(r"/новаярефка (.+)")
@func.new_command(r"/новый реф (.+)")
@func.new_command(r"\+реф (.+)")
@func.new_command(r"\+рефка (.+)")
@func.new_command(r"\+рефкод (.+)")
@func.new_command(r"/добавить рефку (.+)")
@func.new_command(r"добавить рефку (.+)")
async def add_refcode(event: Message):
    arg = event.pattern_match.group(1).strip().lower()
    if not re.match("^[A-Za-z0-9_]*$", arg):
        return await event.reply(phrase.ref.not_regex)
    ref = db.RefCodes()
    if await ref.check_ref(arg) is not None:
        return await event.reply(phrase.ref.already_exists)
    if await ref.get_own(event.sender_id) is not None:
        await ref.add_own(event.sender_id, arg)
        return await event.reply(phrase.ref.edited.format(arg))
    await ref.add_own(event.sender_id, arg)
    return await event.reply(phrase.ref.added.format(arg))


@func.new_command(r"/addrefcode$")
@func.new_command(r"/новыйреф$")
@func.new_command(r"/новаярефка$")
@func.new_command(r"/новый реф$")
@func.new_command(r"\+реф$")
@func.new_command(r"\+рефка$")
@func.new_command(r"\+рефкод$")
@func.new_command(r"/добавить рефку$")
@func.new_command(r"добавить рефку$")
async def add_refcode_empty(event: Message):
    return await event.reply(phrase.ref.notext)


@func.new_command(r"/delrefcode$")
@func.new_command(r"/удалитьреф$")
@func.new_command(r"/удалитьрефку$")
@func.new_command(r"/удалить реф$")
@func.new_command(r"\-реф$")
@func.new_command(r"\-рефка$")
@func.new_command(r"\-рефкод$")
@func.new_command(r"/удалить рефку$")
@func.new_command(r"удалить рефку$")
async def del_refcode(event: Message):
    if await db.RefCodes().delete(event.sender_id) is False:
        return await event.reply(phrase.ref.not_found)
    return await event.reply(phrase.ref.deleted)


@func.new_command(r"/топреф$")
@func.new_command(r"/топрефералов$")
@func.new_command(r"/топрефералы$")
@func.new_command(r"/топ рефералы$")
@func.new_command(r"/топ реф$")
@func.new_command(r"/топ рефералов$")
@func.new_command(r"/рефералы топ$")
async def top_ref(event: Message):
    text = [phrase.ref.top]
    info = await db.RefCodes().get_top_uses()
    n = 1
    for chunk in info:
        text.append(
            f"{n}. **{await func.get_name(int(chunk[0]))}** - {chunk[1]}"
        )
        n += 1
        if n > config.cfg.MaxStatPlayers:
            break
    if n == 1:
        return await event.reply(phrase.ref.top_empty)
    return await event.reply("\n".join(text))


@func.new_command(r"/рефка$")
@func.new_command(r"/рефкод$")
@func.new_command(r"/моярефка$")
@func.new_command(r"/мойрефкод$")
@func.new_command(r"/реферальныйкод$")
@func.new_command(r"/реферальный код$")
@func.new_command(r"/refcode")
async def my_ref(event: Message):
    ref = db.RefCodes()
    name = await ref.get_own(event.sender_id)
    if name is None:
        return await event.reply(phrase.ref.not_found)
    uses = await ref.check_uses(event.sender_id)
    if len(uses) == 0:
        uses = "0"
    else:
        players = []
        for player in uses:
            players.append(await func.get_name(player, minecraft=True))  # noqa: PERF401
        uses = f"{len(uses)}: {', '.join(players)}"
    return await event.reply(phrase.ref.my.format(name=name, uses=uses))
