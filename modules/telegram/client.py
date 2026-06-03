from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from loguru import logger
from telethon import TelegramClient, connection, types


from .. import config, pathes, formatter

logger.info(f"Загружен модуль {__name__}!")


logger.info(f"MTProxy enabled: {config.tokens.mtproxy.enable}")

client = TelegramClient(
    session=pathes.bot,
    api_id=config.tokens.bot.id,
    api_hash=config.tokens.bot.hash,
    device_model="Bot",
    system_version="4.16.30-vxCUSTOM",
    lang_code="ru",
    system_lang_code="ru",
    use_ipv6=config.cfg.UseIPv6,
    connection_retries=-1,
    retry_delay=2,
    proxy=(
        config.tokens.mtproxy.server,
        config.tokens.mtproxy.port,
        config.tokens.mtproxy.secret,
    )
    if config.tokens.mtproxy.enable
    else None,
    connection=connection.ConnectionTcpMTProxyRandomizedIntermediate
    if config.tokens.mtproxy.enable
    else connection.ConnectionTcpFull,
)
client.parse_mode = formatter.CustomMarkdown()

logger.info(f"Aiogram proxy state: {config.tokens.proxy.enabled}")

aio = Bot(
    token=config.tokens.bot.token,
    session=AiohttpSession(
        proxy=f"socks5://{config.tokens.proxy.login}:{config.tokens.proxy.password}@{config.tokens.proxy.host}:{config.tokens.proxy.port}"
        if config.tokens.proxy.enabled
        else None
    ),
)
dp = Dispatcher()

from . import (  # noqa: E402, F401
    actions,
    admins,
    ai,
    base,
    callbacks,
    forum,
    func,
    games,
    mailing,
    misc,
    notes,
    referrals,
    shop,
    states,
    statistic,
    tickets,
    trading,
)
