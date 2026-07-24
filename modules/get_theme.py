from random import choices

from loguru import logger

logger.info(f"Загружен модуль {__name__}!")


def weighted_choice(strings, weights):
    if not isinstance(strings, list) or not all(
        isinstance(s, str) for s in strings
    ):
        logger.error("Все элементы должны быть строками!")
        return None

    if not isinstance(weights, dict):
        logger.error("Веса должны быть словарем.")
        return None

    valid_weights = {
        k: v
        for k, v in weights.items()
        if k in strings and isinstance(v, (int, float))
    }
    if not all(v >= 0 for v in valid_weights.values()):
        logger.error("Веса должны быть неотрицательными числами.")
        return None
    if len(valid_weights) == 0:
        logger.error("Нет валидных весов для строк.")
        return None

    probabilities = [valid_weights.get(s, 0) for s in strings]

    total_weight = sum(probabilities)
    if total_weight > 0:
        normalized_probabilities = [p / total_weight for p in probabilities]
    else:
        normalized_probabilities = probabilities

    try:
        return choices(strings, weights=normalized_probabilities, k=1)[0]
    except IndexError:
        logger.error("Список строк пуст или веса некорректны.")
        return None
