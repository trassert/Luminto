from typing import TYPE_CHECKING

from loguru import logger

from .. import chart, config, crocostat, db, formatter, mcrcon, pathes, phrase
from . import func
from .client import client

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


@func.new_command(
    [
        r"/топ соо(.*)",
        r"/топ сообщений(.*)",
        r"/топ в чате(.*)",
        r"/актив сервера(.*)",
        r"/мчат(.*)",
        r"/мстат(.*)",
    ]
)
async def active_check(event: Message):
    arg = event.pattern_match.group(1).strip()
    days = 0 if arg in phrase.all_arg else (int(arg) if arg.isdigit() else 1)

    stat = db.Statistic(days=days)
    all_data = await stat.get_all()

    if not all_data:
        return await event.reply(phrase.stat.empty)

    players = "\n".join(
        f"{i}. {name} - {count}"
        for i, (name, count) in enumerate(
            all_data[: config.cfg.MaxStatPlayers], 1
        )
    )

    time_str = (
        "всё время"
        if days == 0
        else ("день" if days == 1 else formatter.value_to_str(days, "день"))
    )

    if days == 0 or days >= 7:
        chart.create_plot(await stat.get_raw())
        return await client.send_file(
            event.chat_id,
            pathes.chart,
            caption=phrase.stat.chat.format(time=time_str, text=players),
        )
    return await event.respond(
        phrase.stat.chat.format(time=time_str, text=players)
    )


@func.new_command(
    [
        r"/топ крокодил$",
        r"/топ слова$",
        r"/стат крокодил$",
        r"/стат слова$",
        r"топ крокодила$",
    ]
)
async def crocodile_wins(event: Message):
    all_data = await crocostat.get_all()
    text = "\n".join(
        [
            f"{i}. **{await func.get_name(pid)}**: {wins} побед"
            for i, (pid, wins) in enumerate(all_data.items(), 1)
            if i <= config.cfg.MaxStatPlayers
        ]
    )
    return await event.reply(phrase.crocodile.stat.format(text), silent=True)


@func.new_command(r"/банк$")
async def all_money(event: Message):
    return await event.reply(
        phrase.money.all_money.format(
            formatter.value_to_str(await db.get_all_money(), phrase.currency)
        )
    )


@func.new_command(
    [
        r"/топ игроков(.*)",
        r"/топигроков(.*)",
        r"/topplayers(.*)",
        r"/playtimetop(.*)",
        r"/bestplayers(.*)",
        r"/toppt(.*)",
    ]
)
async def server_top_list(event: Message):
    arg = event.pattern_match.group(1).strip()
    n = (
        max(3, min(30, int(arg)))
        if arg.isdigit()
        else config.cfg.MaxStatPlayers
    )

    try:
        async with mcrcon.Vanilla as rcon:
            text = [phrase.stat.server] + [
                f"{i}. {(await rcon.send(f'papi parse --null %PTM_nickname_top_{i}%')).strip()} - {(await rcon.send(f'papi parse --null %PTM_playtime_top_{i}:luminto%')).strip()}"
                for i in range(1, n + 1)
            ]
        return await event.reply("\n".join(text))
    except TimeoutError:
        return await event.reply(phrase.server.stopped, silent=True)


@func.new_command(
    [
        r"/топ шахтёров",
        r"/топ шахтеров",
        r"/топ шахта",
        r"/topmine",
        r"/minetop",
        r"/bestminers",
    ]
)
async def server_top_mine(event: Message):
    top = [
        f"{i}. {await func.get_name(pid)} - {formatter.value_to_str(amt, 'аметист')}"
        for i, (pid, amt) in enumerate(await db.get_mine_top(), 1)
        if i <= config.cfg.MaxStatPlayers
    ]
    return await event.reply(
        phrase.stat.mine.format("\n".join(top)), silent=True
    )
