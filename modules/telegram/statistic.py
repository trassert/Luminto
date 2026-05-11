from typing import TYPE_CHECKING

from loguru import logger

from .. import chart, config, db, formatter, mcrcon, pathes, phrase
from . import func
from .client import client

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


@func.new_command(r"/топ соо(.*)")
@func.new_command(r"/топ сообщений(.*)")
@func.new_command(r"/топ в чате(.*)")
@func.new_command(r"/актив сервера(.*)")
@func.new_command(r"/мчат(.*)")
@func.new_command(r"/мстат(.*)")
async def active_check(event: Message):
    arg = event.pattern_match.group(1).strip()

    if arg in phrase.all_arg:
        days = 0
    else:
        try:
            days = int(arg)
        except ValueError:
            days = 1

    stat = db.Statistic(days=days)
    all_data = await stat.get_all()

    if not all_data:
        return await event.reply(phrase.stat.empty)

    players = "\n".join(
        f"{i}. {name} - {count}"
        for i, (name, count) in enumerate(all_data, 1)
        if i <= config.cfg.MaxStatPlayers
    )

    if days == 0:
        time_str = "всё время"
    elif days == 1:
        time_str = "день"
    else:
        time_str = formatter.value_to_str(days, "день")

    caption = phrase.stat.chat.format(time=time_str, text=players)

    send_chart = (days == 0) or (days >= 7)
    if send_chart:
        chart.create_plot(await stat.get_raw())
        return await client.send_file(event.chat_id, pathes.chart, caption=caption)
    return await event.respond(caption)


@func.new_command(r"/топ крокодил$")
@func.new_command(r"/топ слова$")
@func.new_command(r"/стат крокодил$")
@func.new_command(r"/стат слова$")
@func.new_command(r"топ крокодила$")
async def crocodile_wins(event: Message):
    all = await db.Crorostat.get_all()
    text = ""
    n = 1
    for id in all:
        if n > config.cfg.MaxStatPlayers:
            break
        text += f"{n}. **{await func.get_name(id)}**: {all[id]} побед\n"
        n += 1
    return await event.reply(phrase.crocodile.stat.format(text), silent=True)


@func.new_command(r"/банк$")
async def all_money(event: Message):
    return await event.reply(
        phrase.money.all_money.format(
            formatter.value_to_str(await db.get_all_money(), phrase.currency),
        ),
    )


@func.new_command(r"/топ игроков(.*)")
@func.new_command(r"/топигроков(.*)")
@func.new_command(r"/topplayers(.*)")
@func.new_command(r"/playtimetop(.*)")
@func.new_command(r"/bestplayers(.*)")
@func.new_command(r"/toppt(.*)")
async def server_top_list(event: Message):
    arg: str = event.pattern_match.group(1).strip()
    n = config.cfg.MaxStatPlayers
    if arg.isdigit():
        n = max(3, min(30, int(arg)))

    try:
        text = [phrase.stat.server]
        async with mcrcon.Vanilla as rcon:
            for number in range(1, n + 1):
                nickname = (
                    await rcon.send(f"papi parse --null %PTM_nickname_top_{number}%")
                ).strip()
                playtime = (
                    await rcon.send(
                        f"papi parse --null %PTM_playtime_top_{number}:luminto%",
                    )
                ).strip()
                text.append(f"{number}. {nickname} - {playtime}")

        return await event.reply("\n".join(text))
    except TimeoutError:
        return await event.reply(phrase.server.stopped, silent=True)


@func.new_command(r"/топ шахтёров")
@func.new_command(r"/топ шахтеров")
@func.new_command(r"/топ шахта")
@func.new_command(r"/topmine")
@func.new_command(r"/minetop")
@func.new_command(r"/bestminers")
async def server_top_mine(event: Message):
    text = []
    n = 1
    for player in await db.get_mine_top():
        if n > config.cfg.MaxStatPlayers:
            break
        text.append(
            f"{n}. {await func.get_name(player[0])} - {formatter.value_to_str(player[1], 'аметист')}",
        )
        n += 1
    return await event.reply(phrase.stat.mine.format("\n".join(text)), silent=True)
