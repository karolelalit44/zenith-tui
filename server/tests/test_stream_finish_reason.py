"""Streamed finish-reason propagation (AGENT_RELIABILITY_PLAN P3.1).

The provider stream must record the last chunk-level ``finish_reason`` on
``_last_finish_reason`` so the agent loop sees length/content-filter stops
instead of a defaulted ``stop``.
"""

from types import SimpleNamespace

import litellm
import pytest

from server.domain.enums import FinishReason
from server.providers.llm_provider import LLMProvider


def _chunk(content: str | None = None, finish: str | None = None, reasoning: str | None = None):
    delta = SimpleNamespace(content=content, reasoning_content=reasoning, tool_calls=None)
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


@pytest.mark.asyncio
async def test_stream_retries_once_before_any_emit(monkeypatch):
    """A transient failure with nothing emitted is retried exactly once."""
    provider = LLMProvider("openai", model="gpt-4o-mini", api_key="sk-test")
    calls = {"n": 0}

    async def fake_acompletion(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Upstream idle timeout exceeded")
        async def gen():
            yield _chunk(content="retried answer")

        return gen()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    chunks: list[str] = []
    async for text, _ in provider._stream_impl([{"role": "user", "content": "hi"}]):
        chunks.append(text)

    assert calls["n"] == 2
    assert "".join(chunks) == "retried answer"


@pytest.mark.asyncio
async def test_stream_retries_empty_chunk_stall(monkeypatch):
    """Idle stall after an empty chunk (no content/reasoning/tool calls) retries."""
    provider = LLMProvider("openai", model="gpt-4o-mini", api_key="sk-test")
    calls = {"n": 0}

    async def fake_acompletion(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            async def gen():
                yield _chunk(content=None, finish=None)
                raise RuntimeError("Upstream idle timeout exceeded")

            return gen()
        async def gen():
            yield _chunk(content="completed")

        return gen()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    chunks: list[str] = []
    async for text, _ in provider._stream_impl([{"role": "user", "content": "hi"}]):
        chunks.append(text)

    assert calls["n"] == 2
    assert "".join(chunks) == "completed"


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_reasoning_emitted(monkeypatch):
    """Reasoning bytes already yielded to the caller must never be replayed."""
    provider = LLMProvider("openai", model="gpt-4o-mini", api_key="sk-test")
    calls = {"n": 0}

    async def fake_acompletion(**kwargs):
        calls["n"] += 1
        async def gen():
            yield _chunk(reasoning="chain of thought")
            raise RuntimeError("mid-stream failure after reasoning")

        return gen()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    seen: list[tuple[str, str | None]] = []
    with pytest.raises(RuntimeError):
        async for text, reasoning in provider._stream_impl([{"role": "user", "content": "hi"}]):
            seen.append((text, reasoning))

    assert calls["n"] == 1
    assert seen == [("", "chain of thought")]


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_content_emitted(monkeypatch):
    """Bytes already yielded to the caller must never be replayed."""
    provider = LLMProvider("openai", model="gpt-4o-mini", api_key="sk-test")
    calls = {"n": 0}

    async def fake_acompletion(**kwargs):
        calls["n"] += 1
        async def gen():
            yield _chunk(content="partial text")
            raise RuntimeError("mid-stream failure after content")

        return gen()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    with pytest.raises(RuntimeError):
        async for _ in provider._stream_impl([{"role": "user", "content": "hi"}]):
            pass

    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_stream_gives_up_after_single_retry(monkeypatch):
    """A persistently failing stream is retried once, then raised."""
    provider = LLMProvider("openai", model="gpt-4o-mini", api_key="sk-test")
    calls = {"n": 0}

    async def fake_acompletion(**kwargs):
        calls["n"] += 1
        raise RuntimeError("persistent upstream failure")

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    with pytest.raises(RuntimeError):
        async for _ in provider._stream_impl([{"role": "user", "content": "hi"}]):
            pass

    assert calls["n"] == 2
