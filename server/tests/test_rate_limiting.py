"""Regression tests for rate-limit / quota handling (todo/02).

Covers:
- _extract_retry_after parses `retryDelay` from the error body (Google puts it
  in a RetryInfo detail, not the HTTP header).
- Quota classification: per-minute free-tier throttling stays recoverable,
  daily/billing exhaustion is terminal.
- stream_completion makes a SINGLE attempt: a rate limit / provider error is
  surfaced as an explicit error event (code + recoverability preserved) with no
  retries, backoff, or sleeps.
- The loop ends the turn after a rate-limit error instead of pausing and
  retrying.
- The client-side request throttle spaces independent call starts.
- The catalog exposes the per-provider `rate_limit` after migration.
"""

import asyncio
import pytest

from server.agents.loop import AgentLoop
from server.agents.llm_stream import stream_completion
from server.domain.errors import RateLimitError
from server.domain.events import EventKind
from server.providers.base import BaseProvider
from server.providers.llm_provider import (
    _classify_provider_error,
    _extract_retry_after,
    _parse_retry_delay,
)
from server.toolkit import create_default_registry


# ---------------------------------------------------------------------------
# _extract_retry_after / _parse_retry_delay
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, headers=None, content=None):
        self.headers = headers or {}
        self.content = content


class _FakeError(Exception):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response


def test_parse_retry_delay_formats():
    assert _parse_retry_delay('"retryDelay": "9.7s"') == pytest.approx(9.7)
    assert _parse_retry_delay('"retryDelay": "9.788501089s"') == pytest.approx(9.788501089)
    assert _parse_retry_delay('"retryDelay": 9.7') == pytest.approx(9.7)
    assert _parse_retry_delay('retryDelay: "9000ms"') == pytest.approx(9.0)
    assert _parse_retry_delay("no delay info here") is None
    assert _parse_retry_delay("") is None


def test_extract_retry_after_reads_retry_delay_from_body():
    """Google embeds the delay in the JSON body (b'...'-wrapped), not a header."""
    err = _FakeError(
        'litellm.RateLimitError: vertex_ai_betaException - b\'{"error": {"message": '
        '"429 Quota exceeded for metric ...", "status": "RESOURCE_EXHAUSTED", '
        '"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", '
        '"retryDelay": "9.788501089s"}]}}\'',
        response=_FakeResponse(headers=None, content=None),
    )
    assert _extract_retry_after(err) == pytest.approx(9.788501089)


def test_extract_retry_after_prefers_header():
    err = _FakeError("rate limited", response=_FakeResponse(headers={"retry-after": "7"}))
    assert _extract_retry_after(err) == 7.0


def test_extract_retry_after_none_when_absent():
    assert _extract_retry_after(_FakeError("plain error")) is None


# ---------------------------------------------------------------------------
# Quota classification
# ---------------------------------------------------------------------------


def test_per_minute_quota_is_recoverable():
    exc = _classify_provider_error(
        RuntimeError(
            "429 Quota exceeded for metric "
            "generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 15"
        ),
        "google",
    )
    assert isinstance(exc, RateLimitError)
    assert exc.recoverable is True


def test_daily_quota_is_not_recoverable():
    exc = _classify_provider_error(RuntimeError("429 free-models-per-day quota reached"), "google")
    assert isinstance(exc, RateLimitError)
    assert exc.recoverable is False


def test_quota_error_carries_parsed_retry_delay():
    exc = _classify_provider_error(
        RuntimeError('429 Quota exceeded ... "retryDelay": "9.788501089s"'), "google"
    )
    assert isinstance(exc, RateLimitError)
    assert exc.retry_after == pytest.approx(9.788501089)


# ---------------------------------------------------------------------------
# stream_completion (single attempt, no retries)
# ---------------------------------------------------------------------------


class _StreamProvider(BaseProvider):
    def __init__(self, error: RateLimitError | None, call: int = 1):
        super().__init__("google", "gemini-test")
        self._error = error
        self._call = call
        self.calls = 0

    async def complete(self, messages, tools=None):
        raise self._error

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        self.calls += 1
        if self.calls == self._call and self._error is not None:
            raise self._error
        yield ("ok", None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["gemini-test"]


def _run_stream(provider, monkeypatch):
    import server.agents.llm_stream as llm_stream

    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(llm_stream.asyncio, "sleep", fake_sleep)
    events = []

    async def consume():
        async for event in stream_completion(provider, [], [], "s1", 1):
            events.append(event)

    asyncio.run(consume())
    return events, sleeps


def test_stream_rate_limit_emits_error_without_retrying(monkeypatch):
    err = RateLimitError(
        "429 Quota exceeded ... free_tier_requests",
        provider="google",
        retry_after=9.7,
        recoverable=True,
    )
    provider = _StreamProvider(err, call=1)
    events, sleeps = _run_stream(provider, monkeypatch)

    assert provider.calls == 1, "a rate limit must not be silently retried"
    assert sleeps == [], "no retry sleep may occur"
    error_events = [e for e in events if e.kind == EventKind.ERROR]
    assert len(error_events) == 1
    assert error_events[0].data.get("code") == "RATE_LIMIT"
    assert error_events[0].data.get("recoverable") is True
    # The friendly copy tells the user how long to wait, not that we are retrying.
    message = error_events[0].data.get("message", "").lower()
    assert "retrying" not in message
    assert "10s" in message
    assert not any(e.kind == EventKind.MESSAGE for e in events)


def test_stream_non_recoverable_quota_emits_clean_error(monkeypatch):
    err = RateLimitError(
        "free-models-per-day quota", provider="google", retry_after=3600, recoverable=False
    )
    provider = _StreamProvider(err, call=1)
    events, sleeps = _run_stream(provider, monkeypatch)

    assert provider.calls == 1, "a terminal quota must not be retried"
    assert sleeps == []
    error_events = [e for e in events if e.kind == EventKind.ERROR]
    assert len(error_events) == 1
    assert error_events[0].data.get("recoverable") is False
    assert "quota" in error_events[0].data.get("message", "").lower()


# ---------------------------------------------------------------------------
# Turn-level behavior on rate limit (no circuit-breaker pauses/retries)
# ---------------------------------------------------------------------------


class _AlwaysRateLimitProvider(BaseProvider):
    def __init__(self):
        super().__init__("rate", "rate-model")

    async def complete(self, messages, tools=None):
        raise RateLimitError("free_tier_requests", provider="rate", retry_after=5, recoverable=True)

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        # An async generator that raises on first iteration (matches LLMProvider).
        if False:
            yield None
        raise RateLimitError("free_tier_requests", provider="rate", retry_after=5, recoverable=True)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["rate-model"]


@pytest.mark.asyncio
async def test_rate_limited_turn_ends_after_single_error(config, monkeypatch):
    """A rate limit is surfaced as ONE explicit error; the loop must not pause
    and re-attempt the turn."""
    import server.agents.llm_stream as llm_stream

    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(llm_stream.asyncio, "sleep", fake_sleep)

    provider = _AlwaysRateLimitProvider()
    agent = AgentLoop(config, provider, tool_registry=create_default_registry())
    events = []
    async for event in agent.process_prompt("Do the work", "s1", [], "build"):
        events.append(event)

    rl_errors = [
        e for e in events if e.kind == EventKind.ERROR and e.data.get("code") == "RATE_LIMIT"
    ]
    assert len(rl_errors) == 1, f"expected a single rate-limit error, got {len(rl_errors)}"
    # The error stays recoverable so the UI can offer a retry affordance.
    assert rl_errors[0].data.get("recoverable") is True
    assert sleeps == [], "no circuit-breaker pause may occur"
    assert not any(
        e.kind == EventKind.THINKING and "waiting" in e.data.get("text", "") for e in events
    )


# ---------------------------------------------------------------------------
# Client-side request throttle
# ---------------------------------------------------------------------------


def test_request_throttle_paces_calls(monkeypatch):
    from server.providers.llm_provider import _RequestThrottle

    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("server.providers.llm_provider.asyncio.sleep", fake_sleep)

    async def run():
        throttle = _RequestThrottle(min_interval=5.0, jitter=0.0)
        first = await throttle.wait()
        second = await throttle.wait()
        return first, second

    first, second = asyncio.run(run())
    assert first == 0.0, "the first call is not throttled"
    assert second == pytest.approx(5.0)
    assert sleeps == [pytest.approx(5.0)]


def test_request_throttle_disabled_when_interval_zero():
    from server.providers.llm_provider import _RequestThrottle

    async def run():
        throttle = _RequestThrottle(min_interval=0.0)
        return await throttle.wait()

    assert asyncio.run(run()) == 0.0


def test_resolve_min_request_interval_uses_catalog_rate_limit(monkeypatch):
    import server.providers.llm_provider as lp

    monkeypatch.setattr(
        lp, "_catalog", {"providers": {"google": {"rate_limit": {"requests_per_minute": 15}}}}
    )
    assert lp._resolve_min_request_interval("google") == pytest.approx(4.0)


def test_resolve_min_request_interval_env_fallback(monkeypatch):
    import server.providers.llm_provider as lp

    monkeypatch.setattr(lp, "_catalog", {"providers": {}})
    monkeypatch.setattr(lp, "_MIN_REQUEST_INTERVAL_DEFAULT", 2.0)
    assert lp._resolve_min_request_interval("openai") == 2.0
    # Providers without a rate limit stay unthrottled by default.
    monkeypatch.setattr(lp, "_MIN_REQUEST_INTERVAL_DEFAULT", 0.0)
    assert lp._resolve_min_request_interval("openai") == 0.0


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_catalog_exposes_rate_limit_after_migration(tmp_path):
    from server.persistence.repositories import load_catalog
    from server.persistence.startup import DatabaseStartupService

    db_file = str(tmp_path / "test.db")
    DatabaseStartupService(db_file).run()
    catalog = load_catalog(db_file)
    assert catalog["providers"]["google"]["rate_limit"] == {"requests_per_minute": 15}
