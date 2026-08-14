from random import choice, choices, randint, sample
from typing import Any

from loguru import logger

from . import config, files, pathes

logger.info(f"Загружен модуль {__name__}!")


def _weighted_choice(
    strings: list[str], weights: dict[str, int | float]
) -> str | None:
    """
    Выбирает строку из списка с учетом весов.
    Args:
        strings: Список строк для выбора
        weights: Словарь весов для каждой строки
    Returns:
        Выбранная строка или None при ошибке
    """
    if not strings:
        logger.error("Список строк пуст!")
        return None
    if not all(isinstance(s, str) for s in strings):
        logger.error("Все элементы должны быть строками!")
        return None
    if not isinstance(weights, dict):
        logger.error("Веса должны быть словарем.")
        return None
    valid_weights = {
        k: v
        for k, v in weights.items()
        if k in strings and isinstance(v, (int, float)) and v >= 0
    }
    if not valid_weights:
        logger.error("Нет валидных весов для строк.")
        return None
    probabilities = [valid_weights.get(s, 0) for s in strings]
    total_weight = sum(probabilities)
    if total_weight == 0:
        logger.error("Сумма весов равна нулю.")
        return None
    normalized_probabilities = [p / total_weight for p in probabilities]
    try:
        return choices(strings, weights=normalized_probabilities, k=1)[0]
    except Exception:
        logger.exception("Ошибка при выборе строки.")
        return None


def _select_new_theme(
    theme_names: list[str],
    last_theme: str | None,
    weights: dict[str, int | float],
) -> str | None:
    """Выбирает новую тему с учетом весов."""
    if not theme_names:
        return None
    if last_theme not in theme_names:
        return theme_names[0]
    available = [t for t in theme_names if t != last_theme]
    if not available:
        return last_theme
    for _ in range(10):
        candidate = _weighted_choice(theme_names, weights)
        if candidate and candidate != last_theme:
            return candidate
    return choice(available)


def _validate_price(price: Any) -> int | None:
    """
    Валидирует и обрабатывает цену.
    Args:
        price: Цена в различных форматах
    Returns:
        Обработанная цена (int) или None при ошибке
    """
    if isinstance(price, list) and len(price) == 2:
        if all(isinstance(p, int) for p in price):
            return randint(price[0], price[1])
        logger.error(f"Некорректный диапазон цены: {price}")
        return None
    if isinstance(price, (int, float)):
        return int(price)
    logger.error(f"Некорректный формат цены: {price}")
    return None


async def update() -> str | None:
    """Обновляет магазин, возвращая новую тему."""
    try:
        shopc_data = await files.load_json_async(pathes.shopc)
        last_theme = (
            shopc_data.get("theme") if isinstance(shopc_data, dict) else None
        )
    except Exception:
        last_theme = None
    all_themes = await files.load_json_async(pathes.shop)
    if not isinstance(all_themes, dict) or not all_themes:
        logger.exception("Файл shop_all.json пуст или не содержит тем.")
        return None
    theme_names = list(all_themes.keys())
    if last_theme in theme_names and len(theme_names) == 1:
        logger.exception("Нет доступных альтернативных тем в shop_all.json")
        return None
    weights = config.cfg.ShopThemeWeights
    new_theme = _select_new_theme(theme_names, last_theme, weights)
    if not new_theme:
        return None
    theme_items = all_themes.get(new_theme, {})
    if not isinstance(theme_items, dict):
        logger.exception(f"Тема '{new_theme}' не содержит предметов")
        return None
    item_names = list(theme_items.keys())
    if len(item_names) < 5:
        logger.exception(
            f"В теме '{new_theme}' недостаточно предметов (минимум 5, найдено {len(item_names)})"
        )
        return None
    selected_items = (
        sample(item_names, 5) if len(item_names) > 5 else item_names[:5]
    )
    current_shop: dict[str, Any] = {"theme": new_theme}
    for item_name in selected_items:
        item_data = theme_items[item_name].copy()
        price = item_data.get("price")
        validated_price = _validate_price(price)
        if validated_price is not None:
            item_data["price"] = validated_price
            current_shop[item_name] = item_data
    await files.save_json_async(pathes.shopc, current_shop, indent=True)
    return new_theme


async def get() -> dict:
    return await files.load_json_async(pathes.shopc)


async def version(update: bool = False) -> int:
    ver = int(await files.load_text_async(pathes.shopver))
    if not update:
        return ver
    ver += 1
    await files.save_text_async(pathes.shopver, str(ver))
    return ver
