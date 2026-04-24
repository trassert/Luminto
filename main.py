import asyncio

from loguru import logger

from modules import log

log.setup()


async def main():
    from modules import config, db, task_gen, tasks, webhooks
    from modules.telegram import games
    from modules.telegram.client import aio, client, dp

    try:
        await db.Users.initialize()

        await client.start(bot_token=config.tokens.bot.token)

        # await webhooks.server()

        await task_gen.UpdateShopTask.create(tasks.update_shop, 2)
        await task_gen.RewardsTask.create(tasks.rewards, "19:00")
        await task_gen.RemoveStatesTask.create(tasks.remove_states, "17:00")
        await task_gen.BackupDBTask.create(tasks.backup_db, "1:00")
        await games.crocodile_onboot()

        logger.info("Бот запущен.")

        await dp.start_polling(aio)

    except Exception as e:
        logger.exception(f"Критическая ошибка в главном цикле: {e}")

    finally:
        logger.warning("Начало процедуры остановки...")
        try:
            await client.disconnect()
        except Exception as e:
            logger.error(f"Ошибка при отключении клиента: {e}")

        logger.success("Бот остановлен.")


if __name__ == "__main__":
    try:
        try:
            import uvloop

            uvloop.run(main())
        except ModuleNotFoundError:
            logger.warning("Uvloop не найден. Использую стандартный asyncio.")
            asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("Получен сигнал прерывания (Ctrl+C). Выход...")
    except Exception as e:
        logger.critical(f"Необработанное исключение: {e}")
