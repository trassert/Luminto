def hellomsg_check(input_id):
    id_str = str(input_id)
    ids_list = files.load_json_sync(pathes.hellomsg)
    if not isinstance(ids_list, list):
        ids_list = []
    if id_str in ids_list:
        return False
    ids_list.append(id_str)
    files.save_json_sync(pathes.hellomsg, ids_list, indent=True)
    return True

hello = (
    "**Приветствую тебя на люминте!**\n"
    "\n"
    "Возможно, тебе понадобится:\n"
    "    Айпи - **/ip**\n"
    "    Онлайн - **/online**\n"
    "    Карта сервера - **/map**\n"
    "    **[Остальные команды](https://wiki.lumintomc.ru/info/bot_commands)**\n"
    "    **[Правила](https://wiki.lumintomc.ru/rules/list)**\n"
    "\n"
    "Есть вопросы?\n"
    "1. Можешь задать их в **нашу поддержку**:\n"
    "    **t.me/lumintoch?direct**\n"
    "2. Можешь посетить **наш канал**:\n"
    "    **lumintoch.t.me**\n"
    "\n"
    "**В общем, приятной игры на сервере, {}!**"
)
    
async def chat_action():
    if not db.hellomsg_check(event.user_id):
        return None
    await asyncio.sleep(WELCOME_DELAY)
    try:
        perms = await client.get_permissions(
            config.chats.chat,
            event.user_id,
        )
        if perms.is_banned or perms.has_left:
            logger.info(
                f"Пользователь {event.user_id} забанен или вышел до приветствия.",
            )
            return None
    except Exception as e:
        logger.info(
            f"Пользователь {event.user_id} отсутствует в чате или ошибка проверки: {e}",
        )
        return None
    return await client.send_message(
        config.chats.chat,
        phrase.chataction.hello.format(user_name),
        link_preview=False,
    )