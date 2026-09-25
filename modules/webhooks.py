import asyncio
import hmac
import ipaddress
from hashlib import md5, sha1, sha256
from urllib.parse import quote

import aiohttp
import aiohttp.web
import orjson
from loguru import logger

from . import config, db, formatter, log, nicks, phrase
from .telegram import func
from .telegram.client import client

logger.info(f"Загружен модуль {__name__}!")


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


async def status(request: aiohttp.web.Request):
    return aiohttp.web.Response(text="ok")


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
        action = data.get("action")

        logger.info(f"GitHub webhook: event={event}, action={action}")

        repo = data["repository"]
        repo_name = phrase.esc(repo["name"])
        repo_url = phrase.href(repo["html_url"])
        is_private = repo["private"]

        async def send(text: str, *, reply: bool = True) -> None:
            await client.send_message(
                config.chats.chat,
                text,
                link_preview=False,
                parse_mode="html",
                reply_to=config.chats.topics.updates if reply else None,
            )

        if event == "star" and action != "deleted":
            logger.info(f"Звезда! Репо {repo_name}")
            sender = data["sender"]
            await send(
                phrase.github.star.format(
                    repo=repo_name,
                    repo_url=repo_url,
                    author=phrase.esc(sender["login"]),
                    author_url=phrase.href(sender["html_url"]),
                ),
                reply=False,
            )
        elif event == "push" and data.get("commits"):
            logger.info(f"Обновление! Репо {repo_name}")
            branch = data["ref"].split("/")[-1]

            for commit in data["commits"]:
                author_name = commit["author"]["name"]
                await send(
                    phrase.github.update.format(
                        repo=repo_name,
                        repo_url=repo_url,
                        branch=f" ({phrase.esc(branch)})"
                        if branch not in ("master", "main")
                        else "",
                        author=(
                            f'<a href="https://github.com/{phrase.href(quote(author_name))}">'
                            f"{phrase.esc(author_name)}</a>"
                        ),
                        message=phrase.esc(commit["message"]),
                        changes=(
                            f'<b><a href="{phrase.href(commit["url"])}">Что изменилось?</a></b>'
                            if not is_private
                            else ""
                        ),
                    ),
                )
        elif (event == "repository" and action == "created") or (
            event == "ping" and data["hook"]["type"] == "Repository"
        ):
            logger.info(f"Новое репо ({event}) - {repo_name}")
            sender = data["sender"]
            await send(
                phrase.github.new.format(
                    repo=repo_name,
                    repo_url=repo_url,
                    type="Приватный" if is_private else "Публичный",
                    author=phrase.esc(sender["login"]),
                    author_url=phrase.href(sender["html_url"]),
                ),
            )
        elif event == "issues" and action == "labeled":
            logger.info(f"Выдан тип! Репо {repo_name}")
            issue = data["issue"]
            label = data["label"]
            await send(
                phrase.github.issue_labeled.format(
                    issue=phrase.esc(issue["title"]),
                    issue_url=phrase.href(issue["html_url"]),
                    label=phrase.esc(label["name"]),
                ),
            )
        elif event == "issues" and action == "opened":
            logger.info(f"Открыт топик! Репо {repo_name}")
            issue = data["issue"]
            issue_body = issue["body"]
            body_text = (
                issue_body.strip() if issue_body else "Описание отсутствует"
            )
            await send(
                phrase.github.issue_opened.format(
                    issue=phrase.esc(issue["title"]),
                    url=phrase.href(issue["html_url"]),
                    body=phrase.esc(body_text),
                ),
            )
        elif event == "issues" and action == "closed":
            logger.info(f"Закрыт топик! Репо {repo_name}")
            issue = data["issue"]
            emoji, reason = phrase.github.close_reasons.get(
                issue["state_reason"],
                ("❌", "Без причины"),
            )
            await send(
                phrase.github.issue_closed.format(
                    emoji=emoji,
                    issue=phrase.esc(issue["title"]),
                    url=phrase.href(issue["html_url"]),
                    reason=reason,
                ),
            )

        return aiohttp.web.Response(text="ok")
    except (orjson.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
        logger.warning(f"Невалидный payload от GitHub: {e}")
        return aiohttp.web.Response(text="Bad request", status=400)


async def hotmc(request: aiohttp.web.Request):
    load = await request.post()
    nick = load["nick"]
    sign = load["sign"]
    time = load["time"]
    logger.success(f"{nick} проголосовал в {time} с хешем {sign}")
    hash = sha1(f"{nick}{time}{config.tokens.hotmc}".encode()).hexdigest()
    if sign != hash:
        logger.warning("Хеш не совпал!")
        logger.warning(f"- Должен быть: {sign}")
        logger.warning(f"- Имеется: {hash}")
        return aiohttp.web.Response(
            text="Unauthorized",
            status=401,
        )
    tg_id = await nicks.get_byname(nick)
    if tg_id is not None:
        await db.add_money(tg_id, config.cfg.VoteGift)
        await db.add_votes(tg_id, 1)
        give = phrase.vote_money.format(
            formatter.value_to_str(config.cfg.VoteGift, phrase.currency),
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
        logger.warning(f"- Должен быть: {sign}")
        logger.warning(f"- Имеется: {hash}")
        return aiohttp.web.Response(
            text="Переданные данные не прошли проверку.",
            status=401,
        )
    tg_id = await nicks.get_byname(username)
    if tg_id is not None:
        await db.add_money(tg_id, config.cfg.VoteGift)
        await db.add_votes(tg_id, 1)
        give = phrase.vote_money.format(
            formatter.value_to_str(config.cfg.VoteGift, phrase.currency),
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
        return aiohttp.web.Response(text="Unauthorized", status=401)
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
            return aiohttp.web.Response(text="Unauthorized", status=401)
        tgid = await nicks.get_byname(data.get("player"))
        if tgid is None:
            logger.warning("Неверный игрок (vip-action)")
            return aiohttp.web.Response(text="Uncorrect player", status=401)
        roles = db.Roles()
        user = await roles.get(tgid)
        if user > roles.VIP:
            logger.warning("Игрок уже имеет VIP или выше (vip-action)")
            return aiohttp.web.Response(
                text="Player already has VIP or higher",
                status=401,
            )
        if user == roles.BLACKLIST:
            logger.warning("Игрок в черном списке (vip-action)")
            return aiohttp.web.Response(
                text="Player is blacklisted",
                status=401,
            )
        await roles.set(tgid, roles.VIP)
        return aiohttp.web.Response(text="ok")
    return aiohttp.web.Response(text="Incorrect action", status=400)


async def bank(request: aiohttp.web.Request):
    if not is_local_request(request):
        return aiohttp.web.Response(text="Forbidden", status=403)
    if request.query.get("key") != config.tokens.bankplugin:
        logger.warning("Неверный пароль (BankPlugin)")
        return aiohttp.web.Response(text="Unauthorized", status=401)
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


async def server():
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
