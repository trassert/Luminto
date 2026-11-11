import json
from collections.abc import AsyncGenerator

import httpx
from groq import AsyncGroq
from loguru import logger

from . import config, files, pathes, phrase

logger.info(f"Загружен модуль {__name__}!")
VALID_ROLES = {"system", "user", "assistant"}


class AI:
    def __init__(self):
        ai_cfg = config.cfg.Ai
        self.model = ai_cfg.Model
        self.max_history_tokens = ai_cfg.MaxHistoryTokens
        self.max_completion_tokens = ai_cfg.MaxCompletionTokens
        self.reasoning_effort = ai_cfg.ReasoningEffort
        self.wiki_timeout = ai_cfg.WikiTimeout
        self.cpt = ai_cfg.CharsPerToken
        self.wiki_base = ai_cfg.WikiBaseUrl
        self.wiki_llms_url = ai_cfg.WikiLlmsUrl
        proxy_str = (
            config.tokens.ai.proxy.proxy_str
            if config.tokens.ai.proxy.enabled
            else None
        )
        self.client = AsyncGroq(
            api_key=config.tokens.ai.token,
            http_client=httpx.AsyncClient(proxy=proxy_str) if proxy_str else None,
        )
        self.history_file = pathes.ai
        self.system_prompt = phrase.ai.prompt
        self.history = None

    def _tokens(self, s):
        return len(s) // self.cpt if s else 0

    def add_to_history(self, role, content):
        self.history.append(
            {"role": "assistant" if role == "assistant" else "user", "content": content}
        )
        start = 1 if self.history[0].get("role") == "system" else 0
        total = sum(self._tokens(m.get("content", "")) for m in self.history)
        while total > self.max_history_tokens and len(self.history) > start + 1:
            total -= self._tokens(self.history.pop(start).get("content", ""))
        if total > self.max_history_tokens:
            logger.warning("История слишком большая. Очищаю до системного промпта.")
            self.history = self.history[:start]

    async def _load(self):
        try:
            data = (
                await files.load_json_async(self.history_file)
                if self.history_file.exists()
                else []
            )
        except Exception as e:
            logger.error(f"Ошибка загрузки истории: {e}. Создаю новую.")
            data = []
        h = [
            {"role": m["role"], "content": m["content"]}
            for m in (data if isinstance(data, list) else [])
            if isinstance(m, dict)
            and m.get("role") in VALID_ROLES
            and m.get("content")
        ]
        if not h:
            return [{"role": "system", "content": self.system_prompt}]
        if h[0]["role"] != "system":
            h.insert(0, {"role": "system", "content": self.system_prompt})
        return h

    async def _save(self):
        clean = [
            m
            for m in self.history
            if m.get("role") in VALID_ROLES and m.get("content")
        ]
        await files.save_json_async(self.history_file, clean)

    async def _wiki_get(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=self.wiki_timeout) as c:
            return (await c.get(url)).text

    async def _call_tool(self, call) -> str:
        name = call.function.name
        if name == "get_wiki_index":
            return await self._wiki_get(self.wiki_llms_url)
        if name == "read_wiki_page":
            try:
                args = json.loads(call.function.arguments or "{}")
                url = str(args.get("url", ""))
            except json.JSONDecodeError:
                return "Некорректные аргументы инструмента."
            if not url.startswith(self.wiki_base):
                return "Можно читать только страницы этой вики."
            return await self._wiki_get(url)
        return f"Неизвестный инструмент: {name}"

    async def _chat(self, stream: bool):
        return await self.client.chat.completions.create(
            model=self.model,
            messages=self.history,
            temperature=1,
            top_p=1,
            max_completion_tokens=self.max_completion_tokens,
            tools=phrase.ai.tools,
            tool_choice="auto",
            reasoning_effort=self.reasoning_effort,
            stream=stream,
        )

    async def generate_response(self, user, prompt) -> AsyncGenerator[str]:
        self.history = self.history or await self._load()
        self.add_to_history(user, prompt)
        full = ""
        try:
            resp = await self._chat(stream=False)
            msg = resp.choices[0].message
            if msg.tool_calls:
                # в history обязаны остаться assistant-сообщение с tool_calls
                # и ответ role=tool на КАЖДЫЙ вызов, иначе Groq отклоняет
                # запрос ("tool call verification failed")
                self.history.append(msg.model_dump(exclude_none=True))
                for call in msg.tool_calls:
                    self.history.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": await self._call_tool(call),
                        }
                    )
                resp = await self._chat(stream=True)
            async for chunk in resp:
                choice = chunk.choices[0] if chunk.choices else None
                if choice and choice.delta.content:
                    full += choice.delta.content
                    yield choice.delta.content
            if not full:
                logger.warning("Пустой ответ модели.")
        finally:
            if full:
                self.add_to_history("assistant", full)
                try:
                    await self._save()
                except Exception as e:
                    logger.error(f"Ошибка сохранения истории: {e}")
            elif self.history[-1].get("role") == "user":
                self.history.pop()  # не храним запрос без ответа


Ai = AI()
