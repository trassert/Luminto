from typing import TYPE_CHECKING

import yaml
from loguru import logger

from . import pathes

if TYPE_CHECKING:
    from pathlib import Path

logger.info(f"Загружен модуль {__name__}!")


class ConfigSection(dict):
    "Конфиг-секции для менеджера. Dict -> ConfigSection."

    def __init__(self, data):
        super().__init__(data)
        for key, value in data.items():
            if isinstance(value, dict):
                self[key] = ConfigSection(value)
            elif isinstance(value, list):
                self[key] = [
                    ConfigSection(i) if isinstance(i, dict) else i
                    for i in value
                ]

    def __getattr__(self, key):
        return self.get(key)


class ConfigManager:
    """Root. Вызывается.
    Пример: config.cfg.bot.token
    """

    def __init__(self, path: Path):
        logger.info(f"Зарегистрирован конфиг {path}")
        raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self._data = ConfigSection(raw_data)

    def __getattr__(self, key):
        return getattr(self._data, key)


cfg = ConfigManager(pathes.config / "config.yml")
tokens = ConfigManager(pathes.config / "tokens.yml")
chats = ConfigManager(pathes.config / "chats.yml")
