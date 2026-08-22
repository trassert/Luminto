from datetime import datetime
from random import choice
from typing import TYPE_CHECKING

from loguru import logger
from telethon import events
from telethon.tl.custom import Button
from telethon.tl.types import (
    KeyboardButtonCallback,
    KeyboardButtonRow,
    Message,
    ReplyInlineMarkup,
)

from .. import files, formatter, pathes, phrase, shop, task_gen
from . import func

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


@func.new_command(
    [r"/shop", r"/шоп$", r"/магазин$", r"магазин$", r"shop$", r"шоп$"]
)
async def shop_command(event: Message):
    shop_data = await shop.get()
    version = await shop.version()
    theme = shop_data.pop("theme")
    theme_data = phrase.shop_quotes[theme]
    items = []
    btns = []

    for i, (name, info) in enumerate(list(shop_data.items())[:5]):
        val = info["value"]
        items.append(
            f"{i + 1}. {name}{f' ({val})' if val != 1 else ''} - {info['price']} {phrase.currency_emoji}"
        )
        btns.append(
            KeyboardButtonCallback(
                text=f"{i + 1}\u20e3", data=f"shop.{i}.{version}".encode()
            )
        )

    return await event.reply(
        phrase.shop.shop.format(
            quote=choice(theme_data["quotes"]),
            emo=theme_data["emo"],
            items="\n".join(items),
            clock=formatter.fmtime(await task_gen.UpdateShopTask.info()),
        ),
        buttons=ReplyInlineMarkup([KeyboardButtonRow(btns)]),
    )


def parse_log_line(line: str) -> tuple:
    parts = line.strip().split("|")
    if len(parts) != 2:
        return None, None, None
    player, item_part = parts
    if "-" in item_part:
        i = item_part.rfind("-")
        item, count = (
            item_part[:i],
            int(item_part[i + 1 :]) if item_part[i + 1 :].isdigit() else 1,
        )
    else:
        item, count = item_part, 1
    return player, item, count


async def get_player_purchases(nick: str, limit: int = 50) -> list[dict]:
    purchases = []
    if not pathes.shop_log.exists():
        return purchases

    for log_file in sorted(pathes.shop_log.glob("*.log")):
        try:
            content = await files.load_text_async(log_file)
            for line in content.splitlines():
                player, item, count = parse_log_line(line)
                if player and player.lower() == nick.lower():
                    date_str = (
                        log_file.stem
                    )  # Аналог .name.replace(".log", ""), но надёжнее
                    purchases.append(
                        {
                            "date": datetime.strptime(date_str, "%Y.%m.%d")
                            if date_str
                            else datetime.now(),
                            "date_str": date_str.replace("2026.", "26.")[:10]
                            if date_str
                            else datetime.now().strftime("%d.%m.%Y"),
                            "item": item,
                            "count": count,
                        }
                    )
        except Exception as e:
            logger.error(f"Ошибка чтения {log_file.name}: {e}")

    return purchases[-limit:] if limit > 0 else purchases


def group_purchases(purchases: list[dict]) -> list[dict]:
    grouped = {}
    for p in purchases:
        key = (p["date_str"], p["item"])
        if key not in grouped:
            grouped[key] = {
                "date": p["date"],
                "date_str": p["date_str"],
                "item": p["item"],
                "total_count": 0,
            }
        grouped[key]["total_count"] += p["count"]

    return sorted(grouped.values(), key=lambda x: x["date"], reverse=True)


def create_pagination_message(
    nick: str, items: list[dict], page: int = 0, per_page: int = 5
) -> tuple:
    total = len(items)
    pages = (total + per_page - 1) // per_page if total > 0 else 1
    page = max(0, min(page, pages - 1))

    msg = phrase.shop.history.format(player_nick=nick)
    if not items:
        return msg + phrase.shop.history_empty, []

    start = page * per_page
    end = min(start + per_page, total)
    page_items = items[start:end]

    msg += phrase.shop.page.format(page=page + 1, total_pages=pages)
    msg += phrase.shop.total_items.format(total_items=total)

    cur_date = None
    for item in page_items:
        if cur_date != item["date_str"]:
            cur_date = item["date_str"]
            msg += f"\n📆 **{cur_date}:**\n"
        msg += phrase.shop.item_line.format(
            item=item["item"], count=item["total_count"]
        )

    buttons = []

    # Кнопки навигации добавляются только если есть куда переходить
    if pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                Button.inline(
                    phrase.shop.btn_back, f"logshop.{nick}.{page - 1}"
                )
            )
        if page < pages - 1:
            nav_buttons.append(
                Button.inline(
                    phrase.shop.btn_forward, f"logshop.{nick}.{page + 1}"
                )
            )

        if nav_buttons:
            buttons.append(nav_buttons)

    buttons.append([Button.inline(phrase.shop.btn_close, "logshop.close")])

    return msg, buttons


@func.new_command(
    [r"/logshop (\S+)", r"/логшоп (\S+)", r"/покупки (\S+)"], min_role=2
)
async def logshop_command(event: Message):
    parts = event.raw_text.split(maxsplit=1)
    if len(parts) < 2:
        return await event.reply(phrase.shop.logshop_use)

    nick = parts[1].strip()
    purchases = await get_player_purchases(nick)
    grouped = group_purchases(purchases)
    msg, btns = create_pagination_message(nick, grouped, 0)

    try:
        return await event.reply(
            msg, buttons=btns or None, parse_mode="markdown"
        )
    except Exception:
        return await event.reply(msg, parse_mode="markdown")


@func.new_callback("logshop", min_role=2)
async def logshop_callback(event: events.CallbackQuery.Event):
    try:
        data_str = event.data.decode()
        logger.info(f"Callback data: {data_str}")

        if data_str == "logshop.close":
            await event.delete()
            return

        if data_str.startswith("logshop."):
            # Надёжный поиск последней точки для отделения номера страницы от никнейма (даже если в нике есть точки)
            last_dot_idx = data_str.rfind(".")
            if last_dot_idx <= len("logshop."):
                await event.answer(
                    f"{phrase.shop.error}: Неверный формат", alert=True
                )
                return

            nick = data_str[len("logshop.") : last_dot_idx]
            page_str = data_str[last_dot_idx + 1 :]

            try:
                page = int(page_str)
            except ValueError:
                await event.answer(
                    f"{phrase.shop.error}: Неверная страница", alert=True
                )
                return

            logger.info(f"Запрос для {nick}, страница {page}")

            purchases = await get_player_purchases(nick)
            grouped = group_purchases(purchases)
            msg, btns = create_pagination_message(nick, grouped, page)

            logger.info(
                f"Сообщение создано, рядов кнопок: {len(btns) if btns else 0}"
            )

            await event.edit(msg, buttons=btns or None, parse_mode="markdown")
            await event.answer()
        else:
            await event.answer(
                f"{phrase.shop.error}: Неверные данные", alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка в logshop_callback: {e}")
        await event.answer(f"{phrase.shop.error}: {str(e)[:50]}", alert=True)


@func.new_command([r"/logshopstats$", r"/статистикапокупок$"], min_role=2)
async def logshop_stats_command(event: Message):
    if not pathes.shop_log.exists():
        return await event.reply(phrase.shop.history_empty)

    total, players, items = 0, set(), set()
    files_count = 0

    for log_file in pathes.shop_log.glob("*.log"):
        files_count += 1
        try:
            for line in (await files.load_text_async(log_file)).splitlines():
                player, item, count = parse_log_line(line)
                if player and item:
                    total += count
                    players.add(player)
                    items.add(item)
        except Exception:
            continue

    msg = phrase.shop.stats.format(
        files=files_count, players=len(players), total=total, items=len(items)
    )
    if items:
        msg += (
            phrase.shop.stats_items
            + "\n"
            + "\n".join(f"  • {item}" for item in sorted(items)[:10])
        )
        if len(items) > 10:
            msg += phrase.shop.stats_more.format(count=len(items) - 10)

    return await event.reply(msg, parse_mode="markdown")
