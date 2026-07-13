import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from . import config, db, formatter, pathes, phrase
from .telegram.client import client

logger.info(f"Загружен модуль {__name__}!")


async def update_shop():
    logger.info("Обновление магазина..")
    try:
        await db.shop_version(update=True)
        theme = await db.update_shop()

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
        tg_id = await db.Nicks(nick=top[0]).get()
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
    logger.info("Проверяем налоги государств..")
    states = db.States.get_all()
    today: datetime = datetime.now()
    today_str = today.strftime("%Y.%m.%d")

    for state_name, state_info in states.items():
        tax_amount = int(state_info.get("tax", 0))
        if tax_amount <= 0:
            continue

        try:
            tax_period = int(state_info.get("tax_period", 7))
        except (TypeError, ValueError):
            tax_period = 7
        if tax_period <= 0:
            tax_period = 7

        last_tax_date = state_info.get("tax_last_date") or today_str
        try:
            last_date = datetime.strptime(last_tax_date, "%Y.%m.%d")
        except ValueError:
            last_date = today

        if (today - last_date).days < tax_period:
            continue

        state = db.State(state_name)
        kicked_players = []
        for player_id in list(state.players):
            balance = await db.get_money(player_id)
            if balance < tax_amount:
                if str(state.tax_nonpayment or "nothing").lower() in (
                    "kick",
                    "кик",
                ):
                    kicked_players.append(player_id)
                    continue
                continue

            await db.add_money(player_id, -tax_amount)
            state.change("money", state.money + tax_amount)

        if kicked_players:
            state.players = [p for p in state.players if p not in kicked_players]
            state.change("players", state.players)
            for player_id in kicked_players:
                player_name = await db.Nicks(id=player_id).get() or player_id
                await client.send_message(
                    entity=config.chats.chat,
                    message=phrase.state.tax_kicked.format(
                        state=state.name,
                        player=player_name,
                    ),
                    reply_to=config.chats.topics.rp,
                )

        state.change("tax_last_date", today_str)


async def remove_states() -> None:
    logger.info("Проверяем пустые государства..")
    states = db.States.get_all()
    today: datetime = datetime.now()
    for state in states:
        state_info = states[state]
        state_date = list(map(int, state_info["date"].split(".")))
        if (len(state_info["players"]) == 0) and (
            today - datetime(state_date[0], state_date[1], state_date[2])
            > timedelta(days=config.cfg.DaysToStatesRemove)
        ):
            await db.add_money(state_info["author"], state_info["money"])
            db.States.remove(state)
            logger.warning(f"Государство {state} распалось")
            await client.send_message(
                entity=config.chats.chat,
                message=phrase.state.end.format(state),
                reply_to=config.chats.topics.rp,
            )


async def backup_db() -> None:
    """
    Таск для создания бекапа папки db и удаления старых бекапов, оставляя только 3 последних.
    """
    src = pathes.db
    if not src.exists():
        logger.warning("Папка db не найдена, пропускаю бекап")
        return

    backup_root = pathes.backup_db
    backup_root.mkdir(parents=True, exist_ok=True)

    date_str: str = datetime.now().strftime("%Y-%m-%d")
    dest: Path = backup_root / date_str
    try:
        shutil.copytree(src, dest, dirs_exist_ok=True)
        logger.info(f"Создан бекап DB: {dest}")
    except Exception:
        logger.exception("Ошибка при создании бекапа базы данных")
        return
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    backups = sorted(
        [p for p in backup_root.iterdir() if p.is_dir() and date_pattern.match(p.name)],
        key=lambda p: p.name,
    )
    if len(backups) > 3:
        for old_backup in backups[:-3]:
            try:
                shutil.rmtree(old_backup)
                logger.info(f"Удалён старый бекап: {old_backup}")
            except Exception:
                logger.exception(f"Не удалось удалить старый бекап: {old_backup}")
