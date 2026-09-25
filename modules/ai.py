from collections.abc import AsyncGenerator

import httpx
from groq import AsyncGroq
from loguru import logger

from . import config, files, pathes, phrase

logger.info(f"Загружен модуль {__name__}!")
CPT, VALID_ROLES = 3, {"system", "user", "assistant"}


class AI:
    def __init__(
        self,
        api_key=config.tokens.ai.token,
        max_history_tokens=5000,
        history_file=pathes.ai,
        system_prompt=phrase.ai.prompt,
        proxy_str="",
        model=config.cfg.AiModel,
    ):
        self.model, self.system_prompt = model, system_prompt
        self.max_history_tokens, self.history_file = (
            max_history_tokens,
            history_file,
        )
        self.client = AsyncGroq(
            api_key=api_key,
            http_client=httpx.AsyncClient(proxy=proxy_str)
            if proxy_str
            else None,
        )
        self.history = None

    def _tokens(self, s):
        return len(s) // CPT if s else 0

    def add_to_history(self, role, content):
        self.history.append(
            {
                "role": "assistant" if role == "assistant" else "user",
                "content": content,
            },
        )
        sys = self.history[0].get("role") == "system"
        start = 1 if sys else 0
        total = sum(self._tokens(m.get("content", "")) for m in self.history)
        while total > self.max_history_tokens and len(self.history) > start + 1:
            total -= self._tokens(self.history.pop(start).get("content", ""))
        if total > self.max_history_tokens:
            logger.warning(
                "История слишком большая. Очищаю до системного промпта.",
            )
            self.history = self.history[:start]

    async def _load(self):
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = (
                await files.load_json_async(self.history_file)
                if self.history_file.exists()
                else []
            )
            if not isinstance(data, list):
                data = []
        except Exception as e:
            logger.error(f"Ошибка загрузки истории: {e}. Создаю новую.")
            data = []
        h = [
            {"role": m["role"], "content": m["content"]}
            for m in data
            if isinstance(m, dict)
            and m.get("role") in VALID_ROLES
            and m.get("content")
        ]
        if not h:
            return [{"role": "system", "content": self.system_prompt}]
        if h[0]["role"] != "system":
            h.insert(0, {"role": "system", "content": self.system_prompt})
        return h

    async def generate_response(self, user, prompt) -> AsyncGenerator[str]:
        self.history = self.history or await self._load()
        self.add_to_history(user, prompt)
        full = ""
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=self.history,
                temperature=1,
                max_completion_tokens=2048,
                top_p=1,
                stream=True,
                stop=None,
                tools=[{"type": "browser_search"}],
            )
            async for chunk in resp:
                if c := chunk.choices[0].delta.content:
                    full += c
                    yield c
        except Exception as e:
            logger.error(f"Ошибка генерации ответа от Groq: {e}")
            if self.history[-1].get("role") == "user":
                self.history.pop()
            raise
        finally:
            if full:
                self.add_to_history("assistant", full)
                try:
                    await files.save_json_async(self.history_file, self.history)
                except Exception as e:
                    logger.error(f"Ошибка сохранения истории: {e}")


Ai = AI(
    proxy_str=config.tokens.ai.proxy.string
    if config.tokens.ai.proxy.enabled
    else None,
)
