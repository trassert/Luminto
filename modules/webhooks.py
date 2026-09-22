import asyncio
import hmac
import ipaddress
from hashlib import md5, sha1, sha256

import aiohttp
import aiohttp.web
import orjson
from loguru import logger

from . import config, db, formatter, log, nicks, phrase
from .telegram import func
from .telegram.client import client

logger.info(f"Загружен модуль {__name__}!")

repos = {
    "LumintoGold": {"chat": -1003408993511, "topic": 72},
    "TrassertTools": {"chat": -1003408993511, "topic": 72},
}


def is_local_request(request: aiohttp.web.Request) -> bool:
    "Check if the request is from a local or private IP address, true or false"
    real_ip = request.headers.get("X-Real-IP")
    if not real_ip:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            real_ip = xff.split(",")[0].strip()

    if not real_ip:
        real_ip = request.remote

    try:
        ip = ipaddress.ip_address(real_ip)
    except ValueError:
        return False
    else:
        return ip.is_loopback or ip.is_private


async def github(request: aiohttp.web.Request) -> aiohttp.web.Response:
    sig = request.headers.get("X-Hub-Signature-256")
    if not sig or "=" not in sig:
        return aiohttp.web.Response(text="Unauthorized", status=401)

    body = await request.read()
    expected = hmac.new(config.tokens.gh.encode(), body, sha256).hexdigest()
    if not hmac.compare_digest(expected, sig.split("=", 1)[1]):
        return aiohttp.web.Response(text="Unauthorized", status=401)

    try:
        data = orjson.loads(body)
        event = request.headers.get("X-GitHub-Event")
        repo = data.get("repository", {})
        repo_name = repo.get("name", "unknown")

        repo_cfg = repos.get(repo_name, {})
        chat_id = repo_cfg.get("chat", config.chats.chat)
        topic_id = repo_cfg.get("topic", config.chats.topics.updates)

        if event == "star" and data.get("action") != "deleted":
            logger.info(f"Звезда! Репо {repo_name}")
            sender = data["sender"]
            await client.send_message(
                chat_id,
                phrase.github.star.format(
                    repo=repo_name,
                    repo_url=repo["html_url"],
                    author=sender["login"],
                    author_url=sender["html_url"],
                ),
                link_preview=False,
            )
        elif event == "push" and data.get("commits"):
            logger.info(f"Обновление! Репо {repo_name}")
            branch = data.get("ref", "").split("/")[-1]
            is_private = repo.get("private", False)

            for commit in data["commits"]:
                author_name = (
                    commit["author"]["name"].replace("[", " ").replace("]", " ")
                )
                await client.send_message(
                    chat_id,
                    phrase.github.update.format(
                        branch=f" ({branch})"
                        if branch not in ("master", "main")
                        else "",
                        author=f"[{author_name}](https://github.com/{author_name})",
                        message=commit["message"],
                        changes=f"**[Что изменилось?]({commit['url']})**"
                        if not is_private
                        else "",
                        repo=f"[{repo_name}](https://github.com/{repo.get('full_name', repo_name)})",
                    ),
                    link_preview=False,
                    reply_to=topic_id,
                )
        elif event == "repository" and data.get("action") == "created":
            logger.info(f"Новое репо - {repo_name}")
            sender = data.get("sender", {})
            await client.send_message(
                chat_id,
                phrase.github.new.format(
                    repo=repo_name,
                    type="Приватный" if repo.get("private") else "Публичный",
                    url=repo["html_url"],
                    author=sender.get("login", "unknown"),
                    author_url=sender.get("html_url", "#"),
                ),
                link_preview=False,
                reply_to=topic_id,
            )

        return aiohttp.web.Response(text="ok")
    except (orjson.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
        logger.warning(f"Невалидный payload от GitHub: {e}")
        return aiohttp.web.Response(text="Bad request", status=400)


async def server():
    async def status(request: aiohttp.web.Request):
        return aiohttp.web.Response(text="ok")

    async def hotmc(request: aiohttp.web.Request):
        load = await request.post()
        nick = load["nick"]
        sign = load["sign"]
        time = load["time"]
        logger.success(f"{nick} проголосовал в {time} с хешем {sign}")
        hash = sha1(f"{nick}{time}{config.tokens.hotmc}".encode()).hexdigest()
        if sign != hash:
            logger.warning("Хеш не совпал!")
            logger.warning(f"Должен быть: {sign}")
            logger.warning(f"Имеется: {hash}")
            return aiohttp.web.Response(
                text="Переданные данные не прошли проверку.",
                status=401,
            )
        tg_id = await nicks.get_byname(nick)
        if tg_id is not None:
            await db.add_money(tg_id, 10)
            await db.add_votes(tg_id, 1)
            give = phrase.vote_money.format(
                formatter.value_to_str(10, phrase.currency),
            )
        else:
            give = ""
        await client.send_message(
            config.chats.chat,
            phrase.hotmc.format(nick=nick, money=give),
            link_preview=False,
        )
        return aiohttp.web.Response(text="ok")

    async def mcservers(request: aiohttp.web.Request):
        load = await request.post()
        username = load["username"]
        sign = load["sign"]
        time = load["time"]
        logger.success(f"{username} проголосовал в {time} с хешем {sign}")
        hash = md5(
            f"{username}|{time}|{config.tokens.mcservers}".encode(),
        ).hexdigest()
        if sign != hash:
            logger.warning("Хеш не совпал!")
            logger.warning(f"Должен быть: {sign}")
            logger.warning(f"Имеется: {hash}")
            return aiohttp.web.Response(
                text="Переданные данные не прошли проверку.",
                status=401,
            )
        tg_id = await nicks.get_byname(username)
        if tg_id is not None:
            await db.add_money(tg_id, 10)
            await db.add_votes(tg_id, 1)
            give = phrase.vote_money.format(
                formatter.value_to_str(10, phrase.currency),
            )
        else:
            give = ""
        await client.send_message(
            config.chats.chat,
            phrase.servers.format(nick=username, money=give),
            link_preview=False,
        )
        return aiohttp.web.Response(text="ok")

    async def minecraft(request: aiohttp.web.Request):
        if not is_local_request(request):
            return aiohttp.web.Response(text="Forbidden", status=403)
        data = await request.post()
        if data.get("password") != config.tokens.chattohttp:
            logger.info("Неверный пароль (C2HTTP)")
            return aiohttp.web.Response(
                text="Password is not valid", status=401
            )
        nick = data.get("nick")
        if not formatter.is_valid_mc_nick(nick):
            return aiohttp.web.Response(text="Nick is not valid", status=406)
        await db.Statistic().add(nick)
        logger.debug(f"+ соо. от {nick}")
        return aiohttp.web.Response(text="ok")

    async def own_actions(request: aiohttp.web.Request):
        if not is_local_request(request):
            return aiohttp.web.Response(text="Forbidden", status=403)
        data = await request.json()
        action = data.get("action")
        if action == "vip":
            if data.get("password") != config.tokens.vipaction:
                logger.info("Неверный пароль (vip-action)")
                return aiohttp.web.Response(
                    text="Password is not valid", status=401
                )
            tgid = await nicks.get_byname(data.get("player"))
            if tgid is None:
                logger.warning("Неверный игрок (vip-action)")
                return aiohttp.web.Response(text="Uncorrect player", status=401)
            roles = db.Roles()
            user = await roles.get(tgid)
            if user > roles.VIP:
                logger.warning("Игрок уже имеет VIP или выше (vip-action)")
                return aiohttp.web.Response(
                    text="Player already has VIP or higher", status=401
                )
            if user == roles.BLACKLIST:
                logger.warning("Игрок в черном списке (vip-action)")
                return aiohttp.web.Response(
                    text="Player is blacklisted", status=401
                )
            await roles.set(tgid, roles.VIP)
            return aiohttp.web.Response(text="ok")
        return aiohttp.web.Response(text="Incorrect action", status=400)

    async def bank(request: aiohttp.web.Request):
        if not is_local_request(request):
            return aiohttp.web.Response(text="Forbidden", status=403)
        if request.query.get("key") != config.tokens.bankplugin:
            logger.warning("Неверный пароль (BankPlugin)")
            return aiohttp.web.Response(text="Uncorrect key", status=401)
        playerid = await nicks.get_byname(request.query.get("player"))
        if playerid is None:
            logger.warning("Неверный игрок (BankPlugin)")
            return aiohttp.web.Response(text="Uncorrect player", status=401)
        amount = int(request.query.get("amount"))
        if not (0 < amount < 67):
            logger.warning("Неверное количество (BankPlugin)")
            return aiohttp.web.Response(text="Uncorrect amount", status=401)
        await client.send_message(
            config.chats.chat,
            phrase.mcadd_money.format(
                player=await func.get_name(playerid, minecraft=True),
                amount=formatter.value_to_str(amount, phrase.currency),
            ),
        )
        await db.add_money(playerid, amount)
        logger.info(f"[Bank] Переведено {amount} на счет {playerid}")
        return aiohttp.web.Response(text="ok")

    app = aiohttp.web.Application()
    app.add_routes(
        [
            aiohttp.web.post("/hotmc", hotmc),
            aiohttp.web.post("/servers", mcservers),
            aiohttp.web.post("/github", github),
            aiohttp.web.post("/minecraft", minecraft),
            aiohttp.web.post("/actions", own_actions),
            aiohttp.web.get("/bank", bank),
            aiohttp.web.get("/", status),
        ],
    )
    runner = aiohttp.web.AppRunner(app, access_log_class=log.AccessLogger)
    await runner.setup()
    ipv4 = aiohttp.web.TCPSite(runner, "127.0.0.1", 5000)
    ipv6 = aiohttp.web.TCPSite(runner, "::1", 5000)
    try:
        await ipv4.start()
        await ipv6.start()
        logger.info("Веб-сервер запущен на порту 5000")
    except KeyboardInterrupt, asyncio.CancelledError:
        logger.info("Остановка веб-сервера...")
        await ipv4.stop()
        await ipv6.stop()
        await runner.cleanup()
        logger.info("Веб-сервер остановлен, порт освобожден.")
