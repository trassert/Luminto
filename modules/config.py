"""
Удобный менеджер конфигов. Доступ к секциям через точку.
Пример:
```python
cfg = ConfigManager("config.yml")
print(cfg.some_variable)
```
"""
import yaml
from loguru import logger

from . import pathes
from pathlib import Path

logger.info(f"Загружен модуль {__name__}!")


class ConfigSection(dict):
    "Конфиг-секции для менеджера. Dict -> ConfigSection."

    def __init__(self, data, default=None):
        super().__init__(data)
        self._default = default
        for key, value in data.items():
            if isinstance(value, dict):
                default_value = None
                if default and key in default:
                    default_value = default[key]
                self[key] = ConfigSection(value, default_value)
            elif isinstance(value, list):
                self[key] = [
                    ConfigSection(i) if isinstance(i, dict) else i
                    for i in value
                ]

    def __getattr__(self, key):
        if key in self:
            return self.get(key)
        if self._default and key in self._default:
            default_value = self._default[key]
            if isinstance(default_value, dict):
                return ConfigSection(default_value)
            return default_value
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{key}'")


class ConfigManager:
    """Root. Вызывается.
    Пример: config.cfg.bot.token
    """

    def __init__(self, path: Path | str, defaults: Path | str = None):
        if isinstance(path, str):
            path = Path(path)
        if isinstance(path, Path):
            path = path
        else:
            raise TypeError(f"path must be Path, got {type(path)}")
        logger.info(f"Зарегистрирован конфиг {path}")

        default_data = None
        if defaults is not None:
            if isinstance(defaults, str):
                defaults = Path(defaults)
            try:
                default_data = yaml.safe_load(defaults.read_text())
            except FileNotFoundError:
                logger.warning(f"Файл дефолтных настроек {defaults} не найден.")

        try:
            data = path.read_text()
        except FileNotFoundError:
            logger.warning(f"Файл конфигурации {path} не найден.")
            if defaults is None:
                raise ValueError("defaults must be provided if config file does not exist.")
            if isinstance(defaults, str):
                path.write_text(defaults)
                data = defaults
            if isinstance(defaults, Path):
                data = defaults.read_text()
                path.write_text(data)
            else:
                raise ValueError(f"defaults must be Path | str, got {type(defaults)}")

        loaded_data = yaml.safe_load(data)
        self._data = ConfigSection(loaded_data, default_data)

    def __getattr__(self, key):
        return getattr(self._data, key)


cfg = ConfigManager(
    pathes.config / "config.yml", defaults=pathes.defaults / "config.yml"
)
tokens = ConfigManager(
    pathes.config / "tokens.yml", defaults=pathes.defaults / "tokens.yml"
)
chats = ConfigManager(
    pathes.config / "chats.yml", defaults=pathes.defaults / "chats.yml"
)
