import re
from datetime import datetime
from random import choice
from typing import TYPE_CHECKING, dict, list, tuple
from loguru import logger
from telethon import events
from telethon.tl.custom import Button
from telethon.tl.types import (
    KeyboardButtonCallback,
    KeyboardButtonRow,
    Message,
    ReplyInlineMarkup,
)
from .. import formatter, phrase, shop, task_gen, pathes, files
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
    items_lines = []
    button_callbacks = []
    for idx, (item_name, item_info) in enumerate(list(shop_data.items())[:5]):
        value = item_info["value"]
        'price = formatter.value_to_str(item_info["price"], phrase.currency)'
        price = f"{item_info['price']} {phrase.currency_emoji}"
        value_str = f" ({value})" if value != 1 else ""
        items_lines.append(f"{idx + 1}. {item_name}{value_str} - {price}")
        button_callbacks.append(
            KeyboardButtonCallback(
                text=f"{idx + 1}\u20e3",
                data=f"shop.{idx}.{version}".encode(),
            ),
        )
    keyboard = ReplyInlineMarkup([KeyboardButtonRow(button_callbacks)])
    formatted_items = "\n".join(items_lines)
    quote = choice(theme_data["quotes"])
    emo = theme_data["emo"]
    clock = formatter.fmtime(await task_gen.UpdateShopTask.info())
    return await event.reply(
        phrase.shop.shop.format(
            quote=quote,
            emo=emo,
            items=formatted_items,
            clock=clock,
        ),
        buttons=keyboard,
    )


def parse_log_line(line: str) -> tuple[str, str, int]:
    """
    Парсит строку лога и возвращает (ник, предмет, количество)
    Пример: Sundox|iron_sword-1 -> ('Sundox', 'iron_sword', 1)
    """
    parts = line.strip().split("|")
    if len(parts) != 2:
        return None, None, None
    player = parts[0]
    item_part = parts[1]
    if "-" in item_part:
        item, count = item_part.rsplit("-", 1)
        try:
            count = int(count)
        except ValueError:
            count = 1
    else:
        item = item_part
        count = 1
    return player, item, count


def get_player_purchases(player_nick: str, limit: int = 50) -> list[dict]:
    """
    Собирает все покупки игрока из всех лог-файлов
    Возвращает список словарей с данными о покупках
    """
    purchases = []
    if not pathes.shop_log.exists():
        return purchases
    log_files = [f for f in pathes.shop_log.iterdir() if f.endswith(".log")]
    log_files.sort()
    for log_file in log_files:
        file_path = pathes.shop_log / log_file
        try:
            f = await files.load_json_async(file_path)
            for line in f:
                player, item, count = parse_log_line(line)
                if player and player.lower() == player_nick.lower():
                    date_str = log_file.replace(".log", "")
                    try:
                        date = datetime.strptime(date_str, "%Y.%m.%d")
                    except ValueError:
                        date = datetime.now()
                    purchases.append(
                        {
                            "date": date,
                            "date_str": date.strftime("%d.%m.%Y"),
                            "item": item,
                            "count": count,
                        }
                    )
        except Exception as e:
            logger.error(f"Ошибка чтения {log_file}: {e}")
    return purchases


def group_purchases(purchases: list[dict]) -> list[dict]:
    """
    Группирует покупки по дате и предмету
    """
    grouped = {}
    for purchase in purchases:
        key = (purchase["date_str"], purchase["item"])
        if key not in grouped:
            grouped[key] = {
                "date": purchase["date"],
                "date_str": purchase["date_str"],
                "item": purchase["item"],
                "total_count": 0,
            }
        grouped[key]["total_count"] += purchase["count"]
    return sorted(grouped.values(), key=lambda x: x["date"], reverse=True)


def create_pagination_message(
    player_nick: str, items: list[dict], page: int = 0, per_page: int = 5
) -> tuple[str, list]:
    """
    Создает сообщение и кнопки для пагинации
    """
    total_items = len(items)
    total_pages = (
        (total_items + per_page - 1) // per_page if total_items > 0 else 1
    )
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, total_items)
    page_items = items[start_idx:end_idx]
    message = phrase.shop.history.format(player_nick=player_nick)
    if not items:
        message += phrase.shop.history_empty
        return message, []
    message += phrase.shop.page.format(page=page + 1, total_pages=total_pages)
    message += phrase.shop.total_items(total_items=total_items)
    current_date = None
    for item in page_items:
        if current_date != item["date_str"]:
            current_date = item["date_str"]
            message += f"\n📆 **{current_date}:**\n"
        message += f"  • {item['item']} — {item['total_count']} шт.\n"
    buttons = []
    nav_buttons = []
    if total_pages > 1:
        if page > 0:
            nav_buttons.append(
                Button.inline("◀️ Назад", f"logshop.{player_nick}.{page - 1}")
            )
        if page < total_pages - 1:
            nav_buttons.append(
                Button.inline("Вперёд ▶️", f"logshop.{player_nick}.{page + 1}")
            )
        if nav_buttons:
            buttons.append(nav_buttons)
    buttons.append([Button.inline("❌ Закрыть", "logshop.close")])
    return message, buttons


@func.new_command([r"/logshop (\S+)", r"/логшоп (\S+)", r"/покупки (\S+)"], min_role=2)
async def logshop_command(event: Message):
    """
    Команда для просмотра покупок игрока
    Использование: /logshop <ник>
    """
    parts = event.raw_text.split(maxsplit=1)
    if len(parts) < 2:
        return await event.reply(phrase.shop.logshop_use)
    player_nick = parts[1].strip()
    purchases = get_player_purchases(player_nick)
    grouped_items = group_purchases(purchases)
    message, buttons = create_pagination_message(player_nick, grouped_items, 0)
    return await event.reply(message, buttons=buttons, parse_mode="markdown")


@func.new_callback("logshop", min_role=2)
async def logshop_callback(event: events.CallbackQuery.Event):
    """
    Обработчик навигации по страницам
    """
    data = event.data.decode("utf-8").split(".")
    if len(data) < 2:
        await event.answer("❌ Ошибка", alert=True)
        return
    action = data[1]
    if action == "close":
        await event.delete()
        return
    if len(data) < 4:
        await event.answer("❌ Ошибка", alert=True)
        return
    player_nick = data[2]
    try:
        page = int(data[3])
    except ValueError:
        page = 0
    purchases = get_player_purchases(player_nick)
    grouped_items = group_purchases(purchases)
    message, buttons = create_pagination_message(
        player_nick, grouped_items, page
    )
    await event.edit(message, buttons=buttons, parse_mode="markdown")
    await event.answer()


@func.new_command([r"/logshopstats$", r"/статистикапокупок$"], min_role=2)
async def logshop_stats_command(event: Message):
    """
    Показывает статистику по всем покупкам
    """
    if not pathes.shop_log.exists():
        return await event.reply(phrase.shop.history_empty)
    total_purchases = 0
    unique_players = set()
    unique_items = set()
    log_files = [f for f in pathes.shop_log.iterdir() if f.is_file() and f.name.endswith(".log")]
    for log_file in log_files:
        file_path = pathes.shop_log / log_file
        try:
            f = await files.load_text_async(file_path)
            for line in f:
                player, item, count = parse_log_line(line)
                if player and item:
                    total_purchases += count
                    unique_players.add(player)
                    unique_items.add(item)
        except Exception:
            continue
    message = "📊 **Статистика покупок**\n\n"
    message += f"📁 Файлов логов: {len(log_files)}\n"
    message += f"👥 Уникальных игроков: {len(unique_players)}\n"
    message += f"📦 Всего покупок: {total_purchases}\n"
    message += f"🎮 Уникальных предметов: {len(unique_items)}\n\n"
    if unique_items:
        message += "**Предметы:**\n"
        for item in sorted(unique_items)[:10]:
            message += f"  • {item}\n"
        if len(unique_items) > 10:
            message += f"  ... и ещё {len(unique_items) - 10}\n"
    return await event.reply(message, parse_mode="markdown")
