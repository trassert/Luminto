import asyncio
import inspect
import time
from datetime import datetime, timedelta
from datetime import time as dt_time
from typing import TYPE_CHECKING, Any, Literal

import aiofiles
import orjson
from loguru import logger

from . import pathes

if TYPE_CHECKING:
    from collections.abc import Callable

logger.info(f"Загружен модуль {__name__}!")

TaskType = Literal["interval", "daily"]
TaskParam = int | str


class Generator:
    _instances: dict[str, Generator] = {}

    def __init__(self, key_name: str, filename: str = pathes.tasks) -> None:
        self.key_name = key_name
        self.filename = filename
        self._task: asyncio.Task | None = None
        self._task_type: TaskType | None = None
        self._task_param: TaskParam | None = None
        self._next_run_timestamp: float | None = None
        logger.info(f"Инициализирован таск-ген {self.key_name}")
        Generator._instances[key_name] = self

    async def create(self, func: Callable, task_param: TaskParam) -> None:
        """Создает периодическую задачу."""
        self.stop()
        if isinstance(task_param, int):
            self._task_type = "interval"
            self._task_param = task_param
            await self._create_interval_task(func, task_param)
        elif isinstance(task_param, str):
            self._task_type = "daily"
            self._task_param = task_param
            await self._create_daily_task(func, task_param)
        else:
            self._task_type = None
            self._task_param = None
            msg = "Параметр времени должен быть int (часы) или str (HH:MM)"
            raise TypeError(
                msg,
            )

    async def _create_interval_task(self, func: Callable, hours: int) -> None:
        """Создает задачу с интервальным выполнением."""
        interval_seconds = hours * 3600
        task_data = await self._get_task_data()
        last_run = task_data.get("last_run")
        current_time = time.time()
        if last_run is None or (current_time - last_run) >= interval_seconds:
            asyncio.create_task(self._safe_execute(func))

            self._next_run_timestamp = current_time + interval_seconds
        else:
            self._next_run_timestamp = last_run + interval_seconds

        self._task = asyncio.create_task(
            self._interval_worker(func, interval_seconds),
        )

    async def _create_daily_task(self, func: Callable, time_str: str) -> None:
        """Создает задачу с ежедневным выполнением."""
        try:
            target_time = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            msg = "Неверный формат времени. Используйте 'HH:MM'."
            raise ValueError(msg)

        self._next_run_timestamp = self._get_next_daily_run(target_time)
        task_data = await self._get_task_data()
        last_run = task_data.get("last_run")

        if last_run is None or last_run < self._next_run_timestamp - 86400:
            asyncio.create_task(self._safe_execute(func))

        self._task = asyncio.create_task(self._daily_worker(func, target_time))

    async def _interval_worker(self, func: Callable, interval: int) -> None:
        """Рабочий для интервальных задач."""
        while True:
            current_time = time.time()

            wait_time = self._next_run_timestamp - current_time
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            await self._safe_execute(func)
            self._next_run_timestamp = time.time() + interval

    async def _daily_worker(self, func: Callable, target_time: dt_time) -> None:
        """Рабочий для ежедневных задач."""
        while True:
            current_time = time.time()

            wait_time = self._next_run_timestamp - current_time
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            await self._safe_execute(func)
            self._next_run_timestamp = self._get_next_daily_run(target_time)

    async def _safe_execute(self, func: Callable) -> None:
        """Безопасно выполняет функцию и сохраняет время запуска."""
        start_time = time.time()
        try:
            if inspect.iscoroutinefunction(func):
                await func()
            else:
                await asyncio.get_event_loop().run_in_executor(None, func)
        except Exception:
            pass
        finally:
            await self._update_task_data(start_time)

    def _get_next_daily_run(self, target_time: dt_time) -> float:
        """Вычисляет временную метку следующего запуска для ежедневной задачи."""
        now = datetime.now()
        target_datetime = datetime.combine(now.date(), target_time)

        if target_datetime <= now:
            target_datetime += timedelta(days=1)
        return target_datetime.timestamp()

    async def _get_all_data(self) -> dict[str, Any]:
        """Получает все данные из файла."""
        try:
            async with aiofiles.open(self.filename, "rb") as f:
                content = await f.read()
                return orjson.loads(content)
        except FileNotFoundError, orjson.JSONDecodeError:
            return {}

    async def _get_task_data(self) -> dict[str, Any]:
        """Получает данные конкретной задачи из файла."""
        all_data = await self._get_all_data()
        return all_data.get(self.key_name, {})

    async def _update_task_data(self, last_run_time: float) -> None:
        """Обновляет время последнего запуска в файле."""
        all_data = await self._get_all_data()

        all_data[self.key_name] = {
            "last_run": last_run_time,
            "task_type": self._task_type,
            "task_param": self._task_param,
        }
        async with aiofiles.open(self.filename, "wb") as f:
            await f.write(orjson.dumps(all_data))

    async def info(self) -> float | None:
        """Возвращает время в секундах до следующего запуска.
        Корректный расчет благодаря хранению _next_run_timestamp.
        """
        if not self._task or not self._next_run_timestamp:
            task_data = await self._get_task_data()
            if not task_data:
                return None

            task_type = task_data.get("task_type")
            task_param = task_data.get("task_param")
            last_run = task_data.get("last_run")
            if not last_run or not task_type or not task_param:
                return None
            if task_type == "interval" and isinstance(task_param, int):
                interval_seconds = task_param * 3600
                next_run = last_run + interval_seconds
            elif task_type == "daily" and isinstance(task_param, str):
                try:
                    target_time = datetime.strptime(task_param, "%H:%M").time()
                    next_run = self._get_next_daily_run(target_time)
                except ValueError:
                    return None
            else:
                return None
            time_until_next = next_run - time.time()
            return max(0, time_until_next)

        time_until_next = self._next_run_timestamp - time.time()
        return max(0, time_until_next)

    def stop(self) -> None:
        """Останавливает задачу и сбрасывает внутренние состояния."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self._next_run_timestamp = None

    @classmethod
    async def cleanup(cls) -> None:
        """Останавливает все задачи."""
        for instance in list(cls._instances.values()):
            instance.stop()
            del cls._instances[instance.key_name]


UpdateShopTask = Generator("UpdateShop")
RewardsTask = Generator("Rewards")
RemoveStatesTask = Generator("RemoveStates")
BackupDBTask = Generator("BackupDB")
TaxTask = Generator("Tax")
