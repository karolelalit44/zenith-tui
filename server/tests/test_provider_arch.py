"""Tests for provider architecture — base, registry, retry, typed interface."""

import pytest

from server.providers.base import (
    BaseProvider,
    ModelInfo,
    ProviderChunk,
    ProviderResponse,
    TokenUsage,
    ToolCall,
    ToolCallDelta,
)
from server.providers.registry import ProviderRegistry
from server.providers.retry import RetryPolicy

# ── ProviderResponse ─────────────────────────────────────────────────────


class TestProviderResponse:
    def test_create_response(self):
        resp = ProviderResponse(content="Hello", model="gpt-4")
        assert resp.content == "Hello"
        assert resp.model == "gpt-4"

    def test_response_with_tool_calls(self):
        tc = ToolCall(id="call_1", name="bash", arguments={"command": "ls"})
        resp = ProviderResponse(content="", tool_calls=[tc])
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "bash"

    def test_response_with_usage(self):
        usage = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        resp = ProviderResponse(content="ok", usage=usage)
        assert resp.usage.total_tokens == 30


# ── ProviderChunk ────────────────────────────────────────────────────────


class TestProviderChunk:
    def test_text_chunk(self):
        chunk = ProviderChunk(delta="Hello")
        assert chunk.delta == "Hello"
        assert chunk.tool_call_delta is None

    def test_tool_call_chunk(self):
        tcd = ToolCallDelta(id="call_1", name="bash", arguments='{"command":')
        chunk = ProviderChunk(tool_call_delta=tcd)
        assert chunk.tool_call_delta.name == "bash"


# ── ModelInfo ────────────────────────────────────────────────────────────


class TestModelInfo:
    def test_model_info(self):
        info = ModelInfo(id="gpt-4", name="GPT-4", provider="openai", context_window=8192)
        assert info.id == "gpt-4"
        assert info.context_window == 8192


# ── ProviderRegistry ─────────────────────────────────────────────────────


class TestProviderRegistry:
    def test_empty_registry(self):
        reg = ProviderRegistry()
        assert reg.list_providers() == []
        assert reg.get("openai") is None

    def test_register_provider(self):
        reg = ProviderRegistry()

        # Register a mock provider
        class MockProvider(BaseProvider):
            def __init__(self):
                super().__init__(name="mock", model="mock-model")

            async def complete(self, messages, **kw):
                return "ok"

            async def stream(self, messages, **kw):
                yield "ok"

            async def validate(self):
                return True

            async def list_models(self):
                return []

        reg.register("mock", MockProvider())
        assert "mock" in reg.list_providers()
        assert reg.get("mock") is not None

    def test_require_missing(self):
        reg = ProviderRegistry()
        with pytest.raises((KeyError, Exception)):
            reg.require("nonexistent")


# ── RetryPolicy ──────────────────────────────────────────────────────────


class TestRetryPolicy:
    def test_default_policy(self):
        p = RetryPolicy()
        assert p.max_retries == 3
        assert p.base_delay > 0

    def test_from_env(self):
        p = RetryPolicy.from_env()
        assert p.max_retries >= 1

    def test_for_stream(self):
        p = RetryPolicy.for_stream()
        assert p.max_retries >= 1

    def test_calculate_delay(self):
        p = RetryPolicy(base_delay=1.0, max_delay=10.0)
        err = TimeoutError("timeout")
        d0 = p.calculate_delay(err, 0)
        d1 = p.calculate_delay(err, 1)
        d2 = p.calculate_delay(err, 2)
        assert d0 <= d1 <= d2 + 0.5  # jitter
        assert d2 <= 10.0

    def test_calculate_delay_rate_limit(self):
        from server.domain.errors import RateLimitError

        p = RetryPolicy(base_delay=1.0, max_delay=10.0)
        err = RateLimitError("rate limited", retry_after=3.0)
        d = p.calculate_delay(err, 0)
        assert d == 3.0  # uses retry_after
