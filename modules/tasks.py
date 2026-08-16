import shutil
from datetime import datetime, timedelta

from loguru import logger

from . import config, db, formatter, nicks, pathes, phrase, shop, states_helper
from .telegram.client import client
from .telegram.states import _check_and_update_tier

logger.info(f"Загружен модуль {__name__}!")


async def update_shop():
    logger.info("Обновление магазина..")
    try:
        await shop.version(update=True)
        theme = await shop.update()

        await client.send_message(
            config.chats.chat,
            phrase.shop.update.format(
                emo=phrase.shop_quotes[theme]["emo"],
                theme=phrase.shop_quotes[theme]["translate"],
            ),
        )
        logger.info("Изменена тема магазина")
    except Exception:
        logger.exception("Ошибка при обновлении шопа")


async def rewards():
    logger.info("Начисление подарков за активность..")
    day_stat = await db.Statistic().get_all()
    for top in day_stat:
        tg_id = await nicks.get_byname(top[0])
        if tg_id is not None:
            await db.add_money(tg_id, config.cfg.ActiveGift)
            logger.info(f"Начислен подарок за активность {top[0]}")
            return await client.send_message(
                config.chats.chat,
                phrase.stat.gift.format(
                    user=top[0],
                    gift=formatter.value_to_str(
                        config.cfg.ActiveGift,
                        phrase.currency,
                    ),
                ),
            )
    return None


async def pay_state_taxes() -> None:
    from .telegram import (
        func,
    )  #! fix has no attribute 'new_command'  # noqa: I001

    logger.info("Проверяем налоги государств..")
    states = await states_helper.get_all()

    for state_name in states.keys():
        logger.info(f"Проверяем налоги государства {state_name}..")
        state = db.State(state_name)
        if state.tax <= 0:
            logger.info(f"Налог государства {state_name} отключён")
            continue
        ptx_result = state.pay_tax()
        for kicked_player in ptx_result["kicked"]:
            await client.send_message(
                entity=config.chats.chat,
                message=phrase.state.tax_kicked.format(
                    player=func.get_name(kicked_player, minecraft=True),
                    state=state_name.capitalize(),
                ),
                reply_to=config.chats.topics.rp,
            )
        await _check_and_update_tier(
            state_name, len(state.players), state.name.capitalize()
        )


async def remove_states() -> None:
    logger.info("Проверяем пустые государства..")
    states = await states_helper.get_all()
    today: datetime = datetime.now()
    for state in states:
        state_info = states[state]
        state_date = list(map(int, state_info["date"].split(".")))
        if (len(state_info["players"]) == 0) and (
            today - datetime(state_date[0], state_date[1], state_date[2])
            > timedelta(days=config.cfg.DaysToStatesRemove)
        ):
            await db.add_money(state_info["author"], state_info["money"])
            await states_helper.remove(state)
            logger.warning(f"Государство {state} распалось")
            await client.send_message(
                entity=config.chats.chat,
                message=phrase.state.end.format(state),
                reply_to=config.chats.topics.rp,
            )


async def backup_db() -> None:
    """Создаёт бекап папки db, оставляет только 3 последних."""
    if not pathes.db.exists():
        logger.warning("Папка db не найдена, пропускаю бекап")
        return

    backup_root = pathes.backup_db
    backup_root.mkdir(parents=True, exist_ok=True)

    dest = backup_root / datetime.now().strftime("%Y-%m-%d")
    try:
        shutil.copytree(pathes.db, dest, dirs_exist_ok=True)
        logger.info(f"Создан бекап DB: {dest}")
    except Exception:
        logger.exception("Ошибка при создании бекапа базы данных")
        return

    backups = sorted(
        [p for p in backup_root.iterdir() if p.is_dir() and len(p.name) == 10 and p.name[4] == '-' and p.name[7] == '-'],
        key=lambda p: p.name
    )
    
    for old_backup in backups[:-3]:
        try:
            shutil.rmtree(old_backup)
            logger.info(f"Удалён старый бекап: {old_backup}")
        except Exception:
            logger.exception(f"Не удалось удалить старый бекап: {old_backup}")