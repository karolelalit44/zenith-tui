from __future__ import annotations

import logging
from typing import AsyncIterator

import time as _time

from .base import AdapterCapabilities, Chunk, ModelAdapter

logger = logging.getLogger(__name__)


class OpenAICompatAdapter(ModelAdapter):
    name = "openai_compat"
    capabilities = AdapterCapabilities(streaming=True, thinking=False, function_calling=True, max_output_tokens=4096)

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        extra_headers: dict | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.extra_headers = extra_headers

    def _build_kwargs(self) -> dict:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key.strip()
        if self.base_url:
            clean_url = self.base_url.removesuffix("/chat/completions").rstrip("/")
            if clean_url:
                kwargs["base_url"] = clean_url
        if self.extra_headers:
            kwargs["extra_headers"] = self.extra_headers
        return kwargs

    async def stream(self, messages: list[dict]) -> AsyncIterator[Chunk]:
        import litellm
        litellm.drop_params = True
        kwargs = self._build_kwargs()
        kwargs["messages"] = messages
        kwargs["stream"] = True
        token_count = 0
        logger.info("OpenAICompat stream START model=%s messages=%d", kwargs.get("model"), len(messages))
        start_ts = _time.monotonic()
        response = await litellm.acompletion(**kwargs)
        async for piece in response:
            choice = piece.choices[0]
            finish = getattr(choice, "finish_reason", None)
            if finish and finish not in ("stop", None, "", "null"):
                logger.warning("OpenAICompat finish_reason=%s", finish)
            delta = choice.delta
            content = delta.content or None
            if content:
                token_count += 1
            yield Chunk(content=content, finish_reason=finish)
        elapsed = _time.monotonic() - start_ts
        logger.info("OpenAICompat stream END tokens=%d elapsed=%.2fs", token_count, elapsed)

    async def complete(self, messages: list[dict]) -> str:
        import litellm
        litellm.drop_params = True
        kwargs = self._build_kwargs()
        kwargs["messages"] = messages
        response = await litellm.acompletion(**kwargs)
        return response.choices[0].message.content or ""
