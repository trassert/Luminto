from time import time

from loguru import logger

from . import config

logger.info(f"Загружен модуль {__name__}!")


class FloodWaitBase:
    def __init__(
        self,
        name="FloodWaitSys",
        timer=5,
        exit_multiplier=3,
        lasttime=time(),
    ) -> None:
        logger.info(f"ФлудВайт: {name} инициализирован")
        self.time = lasttime
        self.timer = timer
        self.exit_multiplier = exit_multiplier

    def request(self) -> int | bool:
        now = time()
        elapsed = now - self.time
        if elapsed >= self.timer:  # Разрешать сразу, если прошло достаточно
            self.time = now
            return 0
        wait_time = self.timer - elapsed
        if (
            wait_time > self.timer * self.exit_multiplier
        ):  # Тасккилл если овер запросов
            return False
        self.time = now + wait_time
        return round(wait_time)  # Возвращаем флудвайт, с уч. будущего


WaitCasino = FloodWaitBase("WaitCasino", config.cfg.Flood.Casino)
WaitPic = FloodWaitBase("WaitPic", config.cfg.Flood.Pic, exit_multiplier=1)
WaitAI = FloodWaitBase("WaitAI", config.cfg.Flood.AI, exit_multiplier=1)
