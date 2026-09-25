from loguru import logger
from sycm import ConfigManager

from . import pathes

logger.info(f"Загружен модуль {__name__}!")

cfg = ConfigManager(
    pathes.config / "config.yml",
    defaults=pathes.defaults / "config.yml",
)
tokens = ConfigManager(
    pathes.config / "tokens.yml",
    defaults=pathes.defaults / "tokens.yml",
)
chats = ConfigManager(
    pathes.config / "chats.yml",
    defaults=pathes.defaults / "chats.yml",
)
