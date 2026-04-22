from collections.abc import AsyncGenerator
from pathlib import Path

import aiofiles
import httpx
import orjson
from groq import AsyncGroq
from loguru import logger

from . import config, pathes, phrase

logger.info(f"Загружен модуль {__name__}!")


class AI:
    def __init__(
        self,
        api_key: str = config.tokens.ai.token,
        max_history: int = config.cfg.AIHistoryLimit,
        history_file: Path = pathes.ai,
        system_prompt: str = phrase.ai.prompt,
        proxy_str: str = "",
    ):
        self.client = AsyncGroq(
            api_key=api_key,
            http_client=httpx.AsyncClient(proxy=proxy_str) if proxy_str else None,
        )
        self.system_prompt = system_prompt
        self.max_history = max_history
        self.history_file = history_file
        self.history = self.get_history()

    def add_to_history(self, role: str, content: str):
        if role == "assistant":
            self.history.append({"role": "assistant", "content": content})
        else:
            self.history.append({"role": "user", "content": f"{role}: {content}"})
        if len(self.history) > self.max_history:
            self.history.pop(1)
            self.history.pop(2)

    async def save_history(self):
        async with aiofiles.open(self.history_file, "wb") as f:
            await f.write(orjson.dumps(self.history))

    async def generate_response(self, user: str, prompt: str) -> AsyncGenerator[str]:
        self.add_to_history(user, prompt)
        response = await self.client.chat.completions.create(
            model=config.cfg.AiModel,
            messages=self.history,
            temperature=1,
            max_completion_tokens=8192,
            top_p=1,
            stream=True,
            stop=None,
            compound_custom={
                "tools": {
                    "enabled_tools": ["web_search", "code_interpreter", "visit_website"]
                }
            },
        )
        full_response = ""
        async for chunk in response:
            if chunk.choices[0].delta.content:
                full_response += chunk.choices[0].delta.content
                yield chunk.choices[0].delta.content
        self.add_to_history("assistant", full_response)
        await self.save_history()

    def get_history(self):
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self.history_file.touch(exist_ok=True)
        with self.history_file.open("rb") as f:
            try:
                return orjson.loads(f.read())
            except Exception:
                return [{"role": "system", "content": self.system_prompt}]


Ai = AI(proxy_str=config.tokens.ai.proxy.string if config.tokens.ai.proxy.enabled else None)
