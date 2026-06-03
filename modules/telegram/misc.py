from typing import TYPE_CHECKING

from loguru import logger

from .. import phrase
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
