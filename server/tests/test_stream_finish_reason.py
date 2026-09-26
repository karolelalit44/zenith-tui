"""Streamed finish-reason propagation (AGENT_RELIABILITY_PLAN P3.1).

The provider stream must record the last chunk-level ``finish_reason`` on
``_last_finish_reason`` so the agent loop sees length/content-filter stops
instead of a defaulted ``stop``.
"""

import asyncio
from types import SimpleNamespace

import litellm
import pytest

from server.domain.enums import FinishReason
from server.domain.errors import ProviderError
from server.providers import llm_provider as llm_provider_module
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


@pytest.mark.asyncio
async def test_stream_retry_logs_backoff_and_error(monkeypatch, caplog):
    """The retry line must carry the backoff and the root error.

    Prod showed bare "attempt=1" lines with no cause; the next 3 AM page
    needs the error inline. Uses the real _stream_impl (no sleep mock —
    one ~2-3s backoff is the honest cost of this test).
    """
    import logging
    import time

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

    with caplog.at_level(logging.WARNING, logger="server.providers.llm_provider"):
        t0 = time.monotonic()
        chunks = [text async for text, _ in provider._stream_impl([{"role": "user", "content": "hi"}])]
        elapsed = time.monotonic() - t0

    assert "".join(chunks) == "retried answer"
    assert elapsed >= 1.5, "backoff sleep must actually run before the retry, not be dead code"
    retry_lines = [r for r in caplog.records if "API STREAM RETRY" in r.getMessage()]
    assert len(retry_lines) == 1
    assert "backoff=" in retry_lines[0].getMessage()
    assert "Upstream idle timeout exceeded" in retry_lines[0].getMessage()


@pytest.mark.asyncio
async def test_stream_ttft_timeout_is_provider_error_never_retried(monkeypatch):
    """A silent pre-first-chunk stream must fail fast as STREAM_TIMEOUT and
    bypass the one-retry gate (retrying would re-cost the full context on the
    same slow provider).
    """
    provider = LLMProvider("openai", model="gpt-4o-mini", api_key="sk-test")
    calls = {"n": 0}

    async def fake_acompletion(**kwargs):
        calls["n"] += 1

        async def gen():
            await asyncio.sleep(2)
            yield _chunk(content="late answer")

        return gen()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm_provider_module, "ZENITH_STREAM_TTFT_TIMEOUT", 0.25)
    monkeypatch.setattr(llm_provider_module, "ZENITH_STREAM_TIMEOUT", 180.0)

    with pytest.raises(ProviderError) as excinfo:
        async for _ in provider._stream_impl([{"role": "user", "content": "hi"}]):
            pass

    assert excinfo.value.code == "STREAM_TIMEOUT"
    assert excinfo.value.recoverable is True
    assert calls["n"] == 1, "STREAM_TIMEOUT must never be retried"


@pytest.mark.asyncio
async def test_stream_total_timeout_is_provider_error_never_retried(monkeypatch):
    """An over-budget stream decays into STREAM_TIMEOUT before any request,
    not into a second full-context request."""
    provider = LLMProvider("openai", model="gpt-4o-mini", api_key="sk-test")
    calls = {"n": 0}

    async def fake_acompletion(**kwargs):
        calls["n"] += 1

        async def gen():
            yield _chunk(content="answer")

        return gen()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm_provider_module, "ZENITH_STREAM_TIMEOUT", -1.0)
    monkeypatch.setattr(llm_provider_module, "ZENITH_STREAM_TTFT_TIMEOUT", 120.0)

    with pytest.raises(ProviderError) as excinfo:
        async for _ in provider._stream_impl([{"role": "user", "content": "hi"}]):
            pass

    assert excinfo.value.code == "STREAM_TIMEOUT"
    assert excinfo.value.recoverable is True
    assert calls["n"] == 0, "no request must be issued once the budget is already spent"


@pytest.mark.asyncio
async def test_stream_dead_stream_never_yields_first_chunk(monkeypatch):
    """A stream that opens but never yields its first chunk must be killed
    within TTFT_TIMEOUT, not hang forever on anext(). This is the
    'silent dead stream' scenario: provider accepts, returns a wrapper,
    then sends nothing."""
    import time

    provider = LLMProvider("openai", model="gpt-4o-mini", api_key="sk-test")
    calls = {"n": 0}

    async def fake_acompletion(**kwargs):
        calls["n"] += 1

        async def gen():
            # Never yield: simulate a provider that accepts but streams nothing.
            await asyncio.sleep(3600)
            if False:  # make this an async generator, not a coroutine
                yield _chunk(content="never")

        return gen()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm_provider_module, "ZENITH_STREAM_TTFT_TIMEOUT", 0.3)
    monkeypatch.setattr(llm_provider_module, "ZENITH_STREAM_TIMEOUT", 180.0)

    t0 = time.monotonic()
    with pytest.raises(ProviderError) as excinfo:
        async for _ in provider._stream_impl([{"role": "user", "content": "hi"}]):
            pass
    elapsed = time.monotonic() - t0

    assert excinfo.value.code == "STREAM_TIMEOUT"
    assert excinfo.value.recoverable is True
    assert calls["n"] == 1, "dead stream must not be retried"
    assert elapsed < 5.0, f"must fail within TTFT budget, took {elapsed:.1f}s"


@pytest.mark.asyncio
async def test_stream_total_timeout_enforced_during_body(monkeypatch):
    """Total timeout is enforced per-chunk inside the stream body: a slow-drip
    provider that yields chunks past ZENITH_STREAM_TIMEOUT must be killed."""
    import time

    provider = LLMProvider("openai", model="gpt-4o-mini", api_key="sk-test")
    calls = {"n": 0}

    async def fake_acompletion(**kwargs):
        calls["n"] += 1

        async def gen():
            yield _chunk(content="fast first")
            # Then stall: next chunk arrives after total timeout.
            await asyncio.sleep(5)
            yield _chunk(content="late second")

        return gen()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm_provider_module, "ZENITH_STREAM_TTFT_TIMEOUT", 2.0)
    monkeypatch.setattr(llm_provider_module, "ZENITH_STREAM_TIMEOUT", 0.5)

    t0 = time.monotonic()
    chunks = []
    with pytest.raises(ProviderError) as excinfo:
        async for text, _ in provider._stream_impl([{"role": "user", "content": "hi"}]):
            chunks.append(text)
    elapsed = time.monotonic() - t0

    assert excinfo.value.code == "STREAM_TIMEOUT"
    assert excinfo.value.recoverable is True
    assert "".join(chunks) == "fast first", "first chunk must be yielded before timeout fires"
    assert elapsed < 3.0, f"must fail within total budget, took {elapsed:.1f}s"
