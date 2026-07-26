from __future__ import annotations

import logging
from typing import AsyncIterator

import time as _time

from .base import AdapterCapabilities, Chunk, ModelAdapter

logger = logging.getLogger(__name__)


class GroqAdapter(ModelAdapter):
    name = "groq"
    capabilities = AdapterCapabilities(streaming=True, thinking=False, function_calling=True, max_output_tokens=2048)

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = (base_url or "https://api.groq.com/openai/v1").rstrip("/")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    async def stream(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[Chunk]:
        client = self._get_client()

        logger.info(
            "Groq stream START model=%s messages=%d tools=%s",
            self.model, len(messages), len(tools) if tools else 0,
        )
        start_ts = _time.monotonic()
        token_count = 0

        clean_messages = self._strip_image_content(messages)

        create_kwargs = dict(
            model=self.model,
            messages=clean_messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
        )
        if tools:
            create_kwargs["tools"] = tools

        response = await client.chat.completions.create(**create_kwargs)

        # Accumulate streaming tool_call deltas by index
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

        # Yield assembled tool calls as a final chunk (if any)
        if _tc_accum:
            assembled = [_tc_accum[i] for i in sorted(_tc_accum.keys())]
            logger.info("Groq stream assembled %d native tool_call(s): %s", len(assembled),
                        [tc["function"]["name"] for tc in assembled])
            yield Chunk(tool_calls=assembled)

        elapsed = _time.monotonic() - start_ts
        logger.info("Groq stream END content_tokens=%d elapsed=%.2fs", token_count, elapsed)

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        client = self._get_client()

        create_kwargs = dict(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=False,
        )
        if tools:
            create_kwargs["tools"] = tools

        response = await client.chat.completions.create(**create_kwargs)
        return response.choices[0].message.content or ""

    def _strip_image_content(self, messages: list[dict]) -> list[dict]:
        """Strip image content from messages — Groq does not support multimodal."""
        clean = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif isinstance(part, str):
                        text_parts.append(part)
                clean.append({**msg, "content": "\n".join(text_parts)})
            else:
                clean.append(msg)
        return clean
