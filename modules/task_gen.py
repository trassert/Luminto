import asyncio
import inspect
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import Any, Literal

from loguru import logger

from . import files, pathes

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
            self._task_type, self._task_param = "interval", task_param
            await self._create_interval_task(func, task_param)
        elif isinstance(task_param, str):
            self._task_type, self._task_param = "daily", task_param
            await self._create_daily_task(func, task_param)
        else:
            self._task_type = self._task_param = None
            msg = "Параметр времени должен быть int (часы) или str (HH:MM)"
            raise TypeError(msg)

    async def _create_interval_task(self, func: Callable, hours: int) -> None:
        """Создает задачу с интервальным выполнением."""
        interval = hours * 3600
        last_run = (await self._get_task_data()).get("last_run")
        now = time.time()
        if last_run is None or now - last_run >= interval:
            asyncio.create_task(self._safe_execute(func))
            self._next_run_timestamp = now + interval
        else:
            self._next_run_timestamp = last_run + interval
        self._task = asyncio.create_task(
            self._worker(func, lambda: time.time() + interval)
        )

    async def _create_daily_task(self, func: Callable, time_str: str) -> None:
        """Создает задачу с ежедневным выполнением."""
        try:
            target_time = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            msg = "Неверный формат времени. Используйте 'HH:MM'."
            raise ValueError(msg)
        self._next_run_timestamp = self._get_next_daily_run(target_time)
        last_run = (await self._get_task_data()).get("last_run")
        if last_run is None or last_run < self._next_run_timestamp - 86400:
            asyncio.create_task(self._safe_execute(func))
        self._task = asyncio.create_task(
            self._worker(func, lambda: self._get_next_daily_run(target_time))
        )

    async def _worker(
        self, func: Callable, next_run: Callable[[], float]
    ) -> None:
        """Рабочий для периодических задач."""
        while True:
            wait = self._next_run_timestamp - time.time()
            if wait > 0:
                await asyncio.sleep(wait)
            await self._safe_execute(func)
            self._next_run_timestamp = next_run()

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
        target = datetime.combine(now.date(), target_time)
        if target <= now:
            target += timedelta(days=1)
        return target.timestamp()

    async def _get_all_data(self) -> dict[str, Any]:
        """Получает все данные из файла."""
        try:
            return await files.load_json_async(Path(self.filename))
        except FileNotFoundError, ValueError:
            return {}

    async def _get_task_data(self) -> dict[str, Any]:
        """Получает данные конкретной задачи из файла."""
        return (await self._get_all_data()).get(self.key_name, {})

    async def _update_task_data(self, last_run_time: float) -> None:
        """Обновляет время последнего запуска в файле."""
        all_data = await self._get_all_data()
        all_data[self.key_name] = {
            "last_run": last_run_time,
            "task_type": self._task_type,
            "task_param": self._task_param,
        }
        await files.save_json_async(Path(self.filename), all_data)

    async def info(self) -> float | None:
        """Возвращает время в секундах до следующего запуска."""
        if self._task and self._next_run_timestamp:
            return max(0, self._next_run_timestamp - time.time())
        data = await self._get_task_data()
        last_run = data.get("last_run")
        task_type = data.get("task_type")
        task_param = data.get("task_param")
        if not last_run or not task_type or not task_param:
            return None
        if task_type == "interval" and isinstance(task_param, int):
            next_run = last_run + task_param * 3600
        elif task_type == "daily" and isinstance(task_param, str):
            try:
                next_run = self._get_next_daily_run(
                    datetime.strptime(task_param, "%H:%M").time()
                )
            except ValueError:
                return None
        else:
            return None
        return max(0, next_run - time.time())

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
        cls._instances.clear()


UpdateShopTask = Generator("UpdateShop")
RewardsTask = Generator("Rewards")
RemoveStatesTask = Generator("RemoveStates")
BackupDBTask = Generator("BackupDB")
TaxTask = Generator("Tax")
DeleteTopicsTask = Generator("DeleteTopics")
