from typing import TYPE_CHECKING

from loguru import logger

from .. import phrase, qr
from . import func

if TYPE_CHECKING:
    from telethon.tl.custom import Message

logger.info(f"Загружен модуль {__name__}!")


@func.new_command(r"/среднее ([\s\S]+)")
async def average(event: Message) -> Message:
    try:
        numbers = list(
            map(
                float,
                event.pattern_match.group(1).strip().replace(",", ".").split(),
            )
        )
        if not numbers:
            return await event.reply(phrase.average_no_numbers)
        average_value = round(sum(numbers) / len(numbers), 2)
        return await event.reply(phrase.average.ok.format(average_value))
    except ValueError:
        return await event.reply(phrase.average_no_numbers)


@func.new_command(r"/qr (.+)")
async def qrgen(event: Message) -> Message:
    data = event.pattern_match.group(1).strip()
    if not data:
        return await event.reply(phrase.qr.no_data)
    try:
        with qr.QR(data) as qrcode:
            path = qrcode.get()
            return await event.reply(phrase.qr.done, file=path)
    except Exception as e:
        logger.error(f"Ошибка при генерации QR-кода: {e}")
        return await event.reply(phrase.qr.error)


@func.new_command(r"/qr$")
async def qrhelp(event: Message) -> Message:
    return await event.reply(phrase.qr.help)