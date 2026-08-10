from typing import TYPE_CHECKING

from loguru import logger

from .. import config, phrase, referrals
from . import func

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


@func.new_command(
    [
        r"/топреф$",
        r"/топрефералов$",
        r"/топрефералы$",
        r"/топ рефералы$",
        r"/топ реф$",
        r"/топ рефералов$",
        r"/рефералы топ$",
    ]
)
async def top_ref(event: Message):
    text = [phrase.ref.top]
    info = await referrals.get_top()

    if not info:
        return await event.reply(phrase.ref.top_empty)

    n = 1
    for user_id, ref_list in info.items():  # items() даёт пары (ключ, значение)
        text.append(
            f"{n}. **{await func.get_name(int(user_id))}** - {len(ref_list)}"
        )
        n += 1
        if n > config.cfg.MaxStatPlayers:
            break

    return await event.reply("\n".join(text))


@func.new_command(
    [
        r"/рефка$",
        r"/рефкод$",
        r"/моярефка$",
        r"/мойрефкод$",
        r"/реферальныйкод$",
        r"/реферальный код$",
        r"/refcode",
        r"/reflink",
        r"/рефссылка",
    ]
)
async def my_ref(event: Message):
    ref = await referrals.check_uses(event.sender_id)
    if len(ref) == 0:
        uses = "0"
    else:
        players = []
        for player in ref:
            players.append(await func.get_name(player, minecraft=True))  # noqa: PERF401
        uses = f"{len(ref)}: {', '.join(players)}"
    return await event.reply(
        phrase.ref.my.format(ref_id=event.sender_id, uses=uses)
    )
