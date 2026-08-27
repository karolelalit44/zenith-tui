"""Streamed finish-reason propagation (AGENT_RELIABILITY_PLAN P3.1).

The provider stream must record the last chunk-level ``finish_reason`` on
``_last_finish_reason`` so the agent loop sees length/content-filter stops
instead of a defaulted ``stop``.
"""

from types import SimpleNamespace

import litellm
import pytest

from server.domain.domain import FinishReason
from server.providers.llm_provider import LLMProvider


def _chunk(content: str | None = None, finish: str | None = None):
    delta = SimpleNamespace(content=content, reasoning_content=None, tool_calls=None)
    choice = SimpleNamespace(delta=delta, finish_reason=finish)
    return SimpleNamespace(choices=[choice], usage=None)


@pytest.mark.asyncio
async def test_stream_propagates_length_finish_reason(monkeypatch):
    provider = LLMProvider("openai", model="gpt-4o-mini", api_key="sk-test")

    async def fake_acompletion(**kwargs):
        async def gen():
            yield _chunk(content="partial ans")
            yield _chunk(finish="length")
            yield _chunk(finish="stop")

        return gen()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    chunks: list[str] = []
    async for text, reasoning in provider._stream_impl([{"role": "user", "content": "hi"}]):
        assert reasoning is None
        chunks.append(text)

    assert "".join(chunks) == "partial ans"
    # The LAST non-null chunk reason wins — here "stop" overrides "length".
    assert provider._last_finish_reason is FinishReason.STOP


@pytest.mark.asyncio
async def test_stream_length_stop_is_visible(monkeypatch):
    provider = LLMProvider("openai", model="gpt-4o-mini", api_key="sk-test")

    async def fake_acompletion(**kwargs):
        async def gen():
            yield _chunk(content="trunca")
            yield _chunk(finish="length")

        return gen()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    async for _ in provider._stream_impl([{"role": "user", "content": "hi"}]):
        pass

    assert provider._last_finish_reason is FinishReason.LENGTH


@pytest.mark.asyncio
async def test_stream_without_chunk_reason_keeps_tool_calls_default(monkeypatch):
    """No chunk reasons at all + no tool calls => stays STOP (legacy behavior)."""
    provider = LLMProvider("openai", model="gpt-4o-mini", api_key="sk-test")

    async def fake_acompletion(**kwargs):
        async def gen():
            yield _chunk(content="plain")

        return gen()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    async for _ in provider._stream_impl([{"role": "user", "content": "hi"}]):
        pass

    assert provider._last_finish_reason is FinishReason.STOP
