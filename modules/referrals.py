from loguru import logger
from typing import Optional, List, Dict, Any
from . import files, pathes, nicks

logger.info(f"Загружен модуль {__name__}!")


async def _get_default_data() -> Dict[str, Any]:
    """Возвращает структуру данных по умолчанию"""
    return {"referrals": {}, "referrers": {}}


async def _load() -> Dict[str, Any]:
    """Загружает данные из файла"""
    try:
        data = await files.load_json_async(pathes.referrals)
        return data
    except FileNotFoundError:
        return await _get_default_data()


async def check_uses(referral_id: int) -> List[int]:
    """
    Проверяет, кто переходил по рефералке
    Args:
        referral_id: ID пользователя, чью рефералку проверяем
    Returns:
        Список ID пользователей, которые перешли по рефералке
    """
    data = await _load()
    users = data["referrals"].get(str(referral_id), [])
    return [int(user_id) for user_id in users]


async def new(referral_id: int, new_user_id: int) -> bool:
    """
    Человек перешёл по рефералке, добавляем в бд
    Args:
        referral_id: ID пользователя, чья рефералка
        new_user_id: ID нового пользователя
    Returns:
        True если добавление успешно, False если пользователь уже есть в системе
    """
    if referral_id == new_user_id:
        logger.info("Пользователь не может пригласить сам себя, пропускаем..")
        return False
    referral_id = str(referral_id)
    new_user_id = str(new_user_id)
    data = await _load()
    if new_user_id in data["referrers"]:
        logger.info(
            f"Пользователь {new_user_id} уже привязан к {data['referrers'][new_user_id]}. Пропускаем.."
        )
        return False
    if referral_id not in data["referrals"]:
        data["referrals"][referral_id] = []
    if new_user_id in data["referrals"][referral_id]:
        logger.info(
            f"Пользователь {new_user_id} уже есть в списке рефералов {referral_id}. Пропускаем.."
        )
        return False
    if await nicks.get_byid(int(new_user_id)) is not None:
        logger.info(f"Пользователь {new_user_id} уже имеет ник. Пропускаем..")
        return False
    data["referrals"][referral_id].append(new_user_id)
    data["referrers"][new_user_id] = referral_id
    await files.save_json_async(pathes.referrals, data, sort_keys=True)
    logger.info(
        f"Пользователь {new_user_id} перешёл по рефералке {referral_id}"
    )
    return True


async def is_ref(user_id: int) -> Optional[int]:
    """
    Проверяет, кто привёл этого человека
    Args:
        user_id: ID пользователя для проверки
    Returns:
        ID того, кто привёл пользователя, или None если он не пришёл по чьей-то рефералке
    """
    data = await _load()
    referrer = data["referrers"].get(str(user_id))
    return int(referrer) if referrer is not None else None


async def get_top() -> Dict[int, List[int]]:
    """
    Выдаёт топ рефоводов
    Returns:
        Словарь вида {id: [новичок1, новичок2, новичок3], ...}
        Отсортирован по убыванию количества рефералов
    """
    data = await _load()
    sorted_items = sorted(
        data["referrals"].items(), key=lambda item: len(item[1]), reverse=True
    )
    return {int(k): [int(user_id) for user_id in v] for k, v in sorted_items}


async def get_referral_count(referral_id: int) -> int:
    """
    Получить количество рефералов у пользователя
    Args:
        referral_id: ID пользователя
    Returns:
        Количество рефералов
    """
    data = await _load()
    return len(data["referrals"].get(str(referral_id), []))
