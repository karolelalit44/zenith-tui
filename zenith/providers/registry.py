from typing import Optional
from .base import BaseProvider
from .llm_provider import LLMProvider
from zenith.config.providers import ProviderConfig
from zenith.core.errors import ConfigError


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, BaseProvider] = {}

    def register(self, name: str, provider: BaseProvider):
        self._providers[name] = provider

    def get(self, name: str) -> Optional[BaseProvider]:
        return self._providers.get(name)

    def require(self, name: str) -> BaseProvider:
        provider = self.get(name)
        if provider is None:
            raise ConfigError(
                f"Provider '{name}' not registered. Available: {list(self._providers.keys()) or 'none'}"
            )
        return provider

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

    @classmethod
    def from_config(cls, providers_config: dict[str, ProviderConfig], active_provider: str) -> "ProviderRegistry":
        registry = cls()
        for name, config in providers_config.items():
            if not config.is_active:
                continue
            provider = LLMProvider(
                name=name,
                api_key=config.api_key,
                base_url=config.base_url,
                model=config.model,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )
            registry.register(name, provider)
        return registry
