from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import time as _time

from .base import Chunk, ModelAdapter

logger = logging.getLogger(__name__)


class NVIDIAAdapter(ModelAdapter):
    name = "nvidia"

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 16384,
        temperature: float = 0.7,
        enable_thinking: bool = False,
        reasoning_budget: int | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = (base_url or "https://integrate.api.nvidia.com/v1").rstrip("/")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.enable_thinking = enable_thinking
        self.reasoning_budget = reasoning_budget

    async def stream(self, messages: list[dict]) -> AsyncIterator[Chunk]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

        extra_body: dict = {"chat_template_kwargs": {}}
        if self.enable_thinking:
            extra_body["chat_template_kwargs"]["enable_thinking"] = True
            if self.reasoning_budget:
                extra_body["reasoning_budget"] = self.reasoning_budget
        else:
            extra_body["chat_template_kwargs"]["thinking"] = False

        logger.info(
            "NVIDIA stream START model=%s messages=%d enable_thinking=%s",
            self.model, len(messages), self.enable_thinking,
        )
        start_ts = _time.monotonic()
        token_count = 0
        reasoning_token_count = 0

        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
            extra_body=extra_body,
        )

        async for chunk in response:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            finish = getattr(choice, "finish_reason", None)
            delta = getattr(choice, "delta", None)
            if not delta:
                continue

            content = delta.content or None
            reasoning = getattr(delta, "reasoning_content", None) or None
            raw_tool_calls = getattr(delta, "tool_calls", None)
            tool_calls = [tc.model_dump() if hasattr(tc, "model_dump") else tc for tc in raw_tool_calls] if raw_tool_calls else None

            if content:
                token_count += 1
            if reasoning:
                reasoning_token_count += 1

            yield Chunk(content=content, reasoning=reasoning, finish_reason=finish, tool_calls=tool_calls)

        elapsed = _time.monotonic() - start_ts
        logger.info(
            "NVIDIA stream END content_tokens=%d reasoning_tokens=%d elapsed=%.2fs",
            token_count, reasoning_token_count, elapsed,
        )

    async def complete(self, messages: list[dict]) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

        extra_body: dict = {"chat_template_kwargs": {}}
        if self.enable_thinking:
            extra_body["chat_template_kwargs"]["enable_thinking"] = True
            if self.reasoning_budget:
                extra_body["reasoning_budget"] = self.reasoning_budget
        else:
            extra_body["chat_template_kwargs"]["thinking"] = False

        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=False,
            extra_body=extra_body,
        )

        return response.choices[0].message.content or ""
