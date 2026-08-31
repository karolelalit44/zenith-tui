import pytest

from server.config.providers import ProviderConfig
from server.providers.base import (
    BaseProvider,
    ModelCapabilities,
    model_capabilities_from_catalog,
)
from server.providers.llm_provider import LLMProvider
from server.providers.registry import ProviderRegistry
from server.providers.token_counter import TokenCounter


class TestTokenCounter:
    def test_count_text(self):
        counter = TokenCounter()
        tokens = counter.count("Hello, World!")
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_count_empty_text(self):
        counter = TokenCounter()
        tokens = counter.count("")
        assert tokens >= 0

    def test_count_messages(self):
        counter = TokenCounter()
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
        ]
        tokens = counter.count_messages(messages)
        assert tokens > 0

    def test_count_messages_empty(self):
        counter = TokenCounter()
        tokens = counter.count_messages([])
        assert tokens == 2

    def test_count_messages_framing(self):
        counter = TokenCounter()
        msg = {"role": "user", "content": "Hi"}
        tokens_single = counter.count_messages([msg])
        assert tokens_single > counter.count("Hi")

    def test_heuristic_fallback(self):
        counter = TokenCounter()
        tokens = counter.count("A" * 100)
        assert tokens > 0

    def test_model_specific_encoding(self):
        counter = TokenCounter()
        count_gpt4 = counter.count("Hello world", model="gpt-4")
        count_gpt35 = counter.count("Hello world", model="gpt-3.5-turbo")
        assert count_gpt4 > 0
        assert count_gpt35 > 0


class TestProviderRegistry:
    def test_empty_registry(self):
        registry = ProviderRegistry()
        assert registry.list_providers() == []

    def test_register_and_get(self):
        registry = ProviderRegistry()
        provider = _create_mock_provider("openai")
        registry.register("openai", provider)
        assert registry.get("openai") is provider

    def test_get_nonexistent(self):
        registry = ProviderRegistry()
        assert registry.get("nonexistent") is None

    def test_list_providers(self):
        registry = ProviderRegistry()
        registry.register("openai", _create_mock_provider("openai"))
        registry.register("anthropic", _create_mock_provider("anthropic"))
        names = registry.list_providers()
        assert "openai" in names
        assert "anthropic" in names

    def test_require_existing(self):
        registry = ProviderRegistry()
        provider = _create_mock_provider("openai")
        registry.register("openai", provider)
        assert registry.require("openai") is provider

    def test_require_missing_raises(self):
        from server.domain.errors import ConfigError

        registry = ProviderRegistry()
        with pytest.raises(ConfigError):
            registry.require("nonexistent")

    def test_from_config(self):
        providers_config = {
            "openai": ProviderConfig(api_key="test-key", model="gpt-4o", is_active=True),
            "anthropic": ProviderConfig(
                api_key="test-key", model="claude-sonnet-4-20250514", is_active=False
            ),
            "groq": ProviderConfig(api_key="test-key", model="", is_active=False),
        }
        registry = ProviderRegistry.from_config(providers_config, "openai")
        assert registry.get("openai") is not None
        assert registry.get("anthropic") is not None
        assert registry.get("groq") is None


class _MockProvider(BaseProvider):
    def __init__(self, name: str = "mock"):
        super().__init__(name, model="mock-model", max_tokens=100, temperature=0.7)

    async def complete(self, messages: list[dict], tools=None) -> str:
        return "mock response"

    async def stream(
        self, messages: list[dict], tools=None, tool_choice=None, response_format=None
    ):
        yield ("mock ", None)
        yield ("stream", None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["mock-model"]


def _create_mock_provider(name: str) -> _MockProvider:
    return _MockProvider(name)


class TestModelCapabilities:
    def test_defaults_when_catalog_missing(self):
        caps = model_capabilities_from_catalog("does-not-exist", "nope", catalog={})
        assert isinstance(caps, ModelCapabilities)
        assert caps.thinking is False
        assert caps.vision is False
        assert caps.functions is True
        assert caps.supports_temperature is True

    def test_resolves_from_catalog(self):
        catalog = {
            "providers": {
                "anthropic": {
                    "models": [
                        {
                            "id": "claude-3",
                            "model_capabilities": {
                                "thinking": True,
                                "vision": True,
                                "function_calling": True,
                            },
                        }
                    ]
                }
            }
        }
        caps = model_capabilities_from_catalog("anthropic", "claude-3", catalog=catalog)
        assert caps.thinking is True
        assert caps.vision is True
        assert caps.functions is True
        assert caps.supports_temperature is True

    def test_aliases_supports_vision_and_supports_functions(self):
        catalog = {
            "providers": {
                "v": {
                    "models": [
                        {
                            "id": "m",
                            "model_capabilities": {"supports_vision": True, "supports_functions": False},
                        }
                    ]
                }
            }
        }
        caps = model_capabilities_from_catalog("v", "m", catalog=catalog)
        assert caps.vision is True
        assert caps.functions is False

    def test_unknown_model_matches_nothing(self):
        catalog = {"providers": {"openai": {"models": [{"id": "a", "model_capabilities": {}}]}}}
        caps = model_capabilities_from_catalog("openai", "b", catalog=catalog)
        assert caps.thinking is False


class TestReasoningEffort:
    def test_llm_provider_accepts_reasoning_effort(self):
        provider = LLMProvider(
            name="openai", model="gpt-4o", api_key="k", reasoning_effort="high"
        )
        assert provider.reasoning_effort == "high"

    def test_reasoning_effort_defaults_none(self):
        provider = LLMProvider(name="openai", model="gpt-4o", api_key="k")
        assert provider.reasoning_effort is None

    def test_capabilities_exposed_on_provider(self):
        provider = LLMProvider(name="openai", model="gpt-4o", api_key="k")
        assert provider.capabilities.thinking is True or provider.capabilities.thinking is False
