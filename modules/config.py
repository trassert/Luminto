"""
Удобный менеджер конфигов. Доступ к секциям через точку.
Пример:
```python
cfg = ConfigManager("config.yml")
print(cfg.some_variable)
```
"""

from pathlib import Path

import yaml
from loguru import logger

from . import pathes

logger.info(f"Загружен модуль {__name__}!")


class ConfigSection(dict):
    def __init__(s, d, def_=None):
        super().__init__(d)
        s._default = def_ or {}
        for k, v in d.items():
            s[k] = (
                ConfigSection(v, s._default.get(k))
                if isinstance(v, dict)
                else [
                    ConfigSection(i, s._default.get(k))
                    if isinstance(i, dict)
                    else i
                    for i in v
                ]
                if isinstance(v, list)
                else v
            )

    def __getattr__(s, k):
        if k in s:
            return s[k]
        if k in s._default:
            v = s._default[k]
            return ConfigSection(v) if isinstance(v, dict) else v
        msg = f"'{type(s).__name__}' has no attribute '{k}'"
        raise AttributeError(msg)


class ConfigManager:
    def __init__(s, path, defaults=None):
        if isinstance(path, str):
            path = Path(path)
        elif not isinstance(path, Path):
            msg = f"path must be Path, got {type(path)}"
            raise TypeError(msg)
        logger.info(f"Зарегистрирован конфиг {path}")
        def_data = s._load_yaml(defaults) if defaults else None
        try:
            raw = path.read_text()
        except FileNotFoundError:
            logger.warning(f"Конфиг {path} не найден.")
            if defaults is None:
                msg = "'defaults' required when config file missing"
                raise ValueError(msg)
            raw = s._resolve_default(defaults, path)
        s._data = ConfigSection(yaml.safe_load(raw), def_data)

    @staticmethod
    def _load_yaml(src):
        p = Path(src) if isinstance(src, str) else src
        try:
            return yaml.safe_load(p.read_text())
        except FileNotFoundError:
            logger.warning(f"Дефолтный конфиг {p} не найден.")
            return None

    @staticmethod
    def _resolve_default(defaults, target):
        data = (
            defaults
            if isinstance(defaults, str)
            else defaults.read_text()
            if isinstance(defaults, Path)
            else None
        )
        if data is None:
            msg = f"'defaults' must be Path | str, got {type(defaults)}"
            raise ValueError(msg)
        target.write_text(data)
        return data

    def __getattr__(s, k):
        return getattr(s._data, k)


cfg = ConfigManager(
    pathes.config / "config.yml", defaults=pathes.defaults / "config.yml"
)
tokens = ConfigManager(
    pathes.config / "tokens.yml", defaults=pathes.defaults / "tokens.yml"
)
chats = ConfigManager(
    pathes.config / "chats.yml", defaults=pathes.defaults / "chats.yml"
)
