from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

import time as _time

from .base import AdapterCapabilities, Chunk, ModelAdapter

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 5.0


class OpenRouterAdapter(ModelAdapter):
    name = "openrouter"
    capabilities = AdapterCapabilities(streaming=True, thinking=True, function_calling=True, max_output_tokens=4096)

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
        self.base_url = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._extra_headers = extra_headers or {}
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            headers = {**self._extra_headers} if self._extra_headers else None
            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                default_headers=headers,
            )
        return self._client

    def _build_kwargs(self, messages: list[dict], tools: list[dict] | None, stream: bool) -> dict:
        kw = dict(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=stream,
        )
        if tools:
            kw["tools"] = tools
        return kw

    async def _call_with_retry(self, messages, tools, stream):
        client = self._get_client()
        last_err = None
        for attempt in range(_MAX_RETRIES):
            try:
                return await client.chat.completions.create(**self._build_kwargs(messages, tools, stream))
            except Exception as e:
                last_err = e
                err_str = str(e)
                if "429" not in err_str:
                    raise
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning("OpenRouter 429 on %s attempt %d, retrying in %.0fs", self.model, attempt + 1, delay)
                await asyncio.sleep(delay)
        raise last_err

    async def stream(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[Chunk]:
        logger.info(
            "OpenRouter stream START model=%s messages=%d tools=%s",
            self.model, len(messages), len(tools) if tools else 0,
        )
        start_ts = _time.monotonic()
        token_count = 0

        response = await self._call_with_retry(messages, tools, stream=True)

        _tc_accum: dict[int, dict] = {}

        async for chunk in response:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            finish = getattr(choice, "finish_reason", None)
            delta = getattr(choice, "delta", None)
            if not delta:
                continue

            content = delta.content or None
            raw_tool_calls = getattr(delta, "tool_calls", None)

            if raw_tool_calls:
                for tc in raw_tool_calls:
                    idx = getattr(tc, "index", 0) or 0
                    func = getattr(tc, "function", None)
                    if func is None:
                        continue
                    if idx not in _tc_accum:
                        _tc_accum[idx] = {
                            "id": getattr(tc, "id", None),
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    name = getattr(func, "name", None)
                    if name:
                        _tc_accum[idx]["function"]["name"] = name
                        if _tc_accum[idx]["id"] is None:
                            _tc_accum[idx]["id"] = getattr(tc, "id", None)
                    args = getattr(func, "arguments", None) or ""
                    if args:
                        _tc_accum[idx]["function"]["arguments"] += args

            if content:
                token_count += 1

            yield Chunk(content=content, finish_reason=finish)

        if _tc_accum:
            assembled = [_tc_accum[i] for i in sorted(_tc_accum.keys())]
            logger.info("OpenRouter stream assembled %d native tool_call(s): %s", len(assembled),
                        [tc["function"]["name"] for tc in assembled])
            yield Chunk(tool_calls=assembled)

        elapsed = _time.monotonic() - start_ts
        logger.info("OpenRouter stream END content_tokens=%d elapsed=%.2fs", token_count, elapsed)

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        response = await self._call_with_retry(messages, tools, stream=False)
        return response.choices[0].message.content or ""
