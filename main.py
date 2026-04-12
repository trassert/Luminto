import asyncio

from loguru import logger

from modules import log

log.setup()


async def main():
    from modules import config, db, task_gen, tasks, webhooks
    from modules.telegram import games
    from modules.telegram.client import aio, client, dp

    await db.Users.initialize()
    await client.start(bot_token=config.tokens.bot.token)  # ty:ignore[invalid-await]
    await webhooks.server()
    await task_gen.UpdateShopTask.create(tasks.update_shop, 2)
    await task_gen.RewardsTask.create(tasks.rewards, "19:00")
    await task_gen.RemoveStatesTask.create(tasks.remove_states, "17:00")
    await task_gen.BackupDBTask.create(tasks.backup_db, "1:00")
    await games.crocodile_onboot()
    await dp.start_polling(aio)
    # await client.run_until_disconnected() Unused if dp is here


if __name__ == "__main__":
    try:
        try:
            import uvloop

            uvloop.run(main())
        except ModuleNotFoundError:
            logger.warning(
                "Uvloop не найден! Установите его для большей производительности",
            )
            asyncio.run(main())
    except KeyboardInterrupt, asyncio.CancelledError:
        logger.warning("Закрываю бота!")
