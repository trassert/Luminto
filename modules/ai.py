from collections.abc import AsyncGenerator
from pathlib import Path

import aiofiles
import httpx
import orjson
from groq import AsyncGroq
from loguru import logger

from . import config, pathes, phrase

logger.info(f"Загружен модуль {__name__}!")
CHARS_PER_TOKEN = 3
VALID_ROLES = {"system", "user", "assistant"}


class AI:
    def __init__(
        self,
        api_key: str = config.tokens.ai.token,
        max_history_tokens: int = 5000,
        history_file: Path = pathes.ai,
        system_prompt: str = phrase.ai.prompt,
        proxy_str: str = "",
        model: str = config.cfg.AiModel,
    ):
        self.model = model
        self.client = AsyncGroq(
            api_key=api_key,
            http_client=httpx.AsyncClient(proxy=proxy_str)
            if proxy_str
            else None,
        )
        self.system_prompt = system_prompt
        self.max_history_tokens = max_history_tokens
        self.history_file = history_file
        self.history = self._load_and_validate_history()

    def _estimate_tokens(self, text: str) -> int:
        return len(text) // CHARS_PER_TOKEN if text else 0

    def _trim_history(self):
        start_idx = 0
        if self.history and self.history[0].get("role") == "system":
            start_idx = 1
        current_tokens = sum(
            self._estimate_tokens(msg.get("content", ""))
            for msg in self.history
        )
        while (
            current_tokens > self.max_history_tokens
            and len(self.history) > start_idx + 1
        ):
            removed_msg = self.history.pop(start_idx)
            current_tokens -= self._estimate_tokens(
                removed_msg.get("content", "")
            )
        if current_tokens > self.max_history_tokens:
            logger.warning(
                "История слишком большая. Очищаю до системного промпта."
            )
            if start_idx > 0:
                self.history = [self.history[0]]
            else:
                self.history = []

    def add_to_history(self, role: str, content: str):
        clean_role = "user" if role != "assistant" else "assistant"
        msg = {"role": clean_role, "content": content}
        self.history.append(msg)
        self._trim_history()

    async def save_history(self):
        try:
            async with aiofiles.open(self.history_file, "wb") as f:
                await f.write(orjson.dumps(self.history))
        except Exception as e:
            logger.error(f"Ошибка сохранения истории: {e}")

    def _load_and_validate_history(self) -> list:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.history_file.exists():
            return [{"role": "system", "content": self.system_prompt}]
        try:
            with self.history_file.open("rb") as f:
                data = orjson.loads(f.read())
                if not isinstance(data, list):
                    return [{"role": "system", "content": self.system_prompt}]
                valid_history = []
                for msg in data:
                    if (
                        isinstance(msg, dict)
                        and msg.get("role") in VALID_ROLES
                        and msg.get("content")
                    ):
                        clean_msg = {
                            "role": msg["role"],
                            "content": msg["content"],
                        }
                        valid_history.append(clean_msg)
                if not valid_history:
                    return [{"role": "system", "content": self.system_prompt}]
                if valid_history[0].get("role") != "system":
                    valid_history.insert(
                        0, {"role": "system", "content": self.system_prompt}
                    )
                return valid_history
        except Exception as e:
            logger.error(f"Ошибка загрузки истории: {e}. Создаю новую.")
            return [{"role": "system", "content": self.system_prompt}]

    async def generate_response(
        self, user: str, prompt: str
    ) -> AsyncGenerator[str]:
        self.add_to_history(user, prompt)
        self.history = [
            msg for msg in self.history if msg.get("role") in VALID_ROLES
        ]
        full_response = ""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=self.history,
                temperature=1,
                max_completion_tokens=2048,
                top_p=1,
                stream=True,
                stop=None,
                tools=[{"type": "browser_search"}],
            )
            async for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_response += delta.content
                    yield delta.content
        except Exception as e:
            logger.error(f"Ошибка генерации ответа от Groq: {e}")
            if self.history and self.history[-1].get("role") == "user":
                self.history.pop()
            raise
        finally:
            if full_response:
                self.add_to_history("assistant", full_response)
                await self.save_history()


Ai = AI(
    proxy_str=config.tokens.ai.proxy.string
    if config.tokens.ai.proxy.enabled
    else None
)
