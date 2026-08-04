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


class TestProviderChunk:
    def test_text_chunk(self):
        chunk = ProviderChunk(delta="Hello")
        assert chunk.delta == "Hello"
        assert chunk.tool_call_delta is None

    def test_tool_call_chunk(self):
        tcd = ToolCallDelta(id="call_1", name="bash", arguments='{"command":')
        chunk = ProviderChunk(tool_call_delta=tcd)
        assert chunk.tool_call_delta.name == "bash"


class TestModelInfo:
    def test_model_info(self):
        info = ModelInfo(id="gpt-4", name="GPT-4", provider="openai", context_window=8192)
        assert info.id == "gpt-4"
        assert info.context_window == 8192


class TestProviderRegistry:
    def test_empty_registry(self):
        reg = ProviderRegistry()
        assert reg.list_providers() == []
        assert reg.get("openai") is None

    def test_register_provider(self):
        reg = ProviderRegistry()

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


