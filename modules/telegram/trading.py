import urllib.parse
from typing import TYPE_CHECKING

from loguru import logger
from telethon import Button

from .. import config, db, formatter, phrase
from . import func
from .client import client

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


async def _ask_int(conv, event, prompt, error_not_int, error_not_positive):
    """Универсальный диалог ввода целого положительного числа."""
    while True:
        await conv.send_message(prompt)
        try:
            resp = await conv.get_response()
        except TimeoutError:
            await event.reply(phrase.trade.timeout)
            return None

        text = resp.raw_text.strip().lower()
        if text == "/стоп":
            await conv.send_message(phrase.trade.cancel)
            return None
        if not text.isdigit():
            await conv.send_message(error_not_int)
            continue

        value = int(text)
        if value < 1:
            await conv.send_message(error_not_positive)
            continue

        return value


async def _trade_flow(
    event, item_key: str, done_template: str, ok_template: str
):
    """Общая логика +товар и +заказ."""
    if not event.is_private:
        return await event.reply(phrase.trade.private)

    username = await func.get_simple_push(event.sender_id)
    if username is None:
        return await event.reply(phrase.trade.username)

    arg = event.pattern_match.group(1).strip().lower()

    async with client.conversation(event.sender_id, timeout=300) as conv:
        count = await _ask_int(
            conv,
            event,
            phrase.trade.count
            if item_key == "sell"
            else phrase.trade.count_for_buy,
            phrase.trade.count_is_int,
            phrase.trade.more_than_0,
        )
        if count is None:
            return None

        price = await _ask_int(
            conv,
            event,
            phrase.trade.price,
            phrase.trade.price_is_int,
            phrase.trade.more_than_0,
        )
        if price is None:
            return None

    parsed_text = urllib.parse.quote(
        f"Хочу купить у тебя {arg}. Предложение актуально?"
        if item_key == "sell"
        else f"У меня есть {arg}. Могу продать тебе!"
    )
    url = f"https://t.me/{username}?text={parsed_text}"

    message: Message = await client.send_message(
        config.chats.chat,
        done_template.format(
            item=arg,
            count=count,
            price=formatter.value_to_str(price, phrase.currency),
        ),
        reply_to=config.chats.topics.trade,
        buttons=[
            [
                Button.url(
                    "🛒 Купить" if item_key == "sell" else "🛒 Продать", url
                ),
            ]
        ],
    )

    await db.add_item(message.id, event.sender_id, arg, count, price)
    return await event.reply(
        ok_template.format(
            item=arg.capitalize(),
            price=formatter.value_to_str(price, phrase.currency),
            count=count,
            id=message.id,
        ),
    )


@func.new_command(r"\+товар (.+)")
async def add_trade(event: Message):
    return await _trade_flow(event, "sell", phrase.trade.done, phrase.trade.ok)


@func.new_command(r"\+заказ (.+)")
async def add_buy(event: Message):
    return await _trade_flow(
        event, "buy", phrase.trade.done_buy, phrase.trade.ok_buy
    )
