"""Provider registry — factory and lookup for LLM providers.

Provides:
- ProviderRegistry: register/get/require providers
- from_config(): create registry from ProviderConfig dict
- get_model_capabilities(): query model capabilities from catalog
"""

from __future__ import annotations

import logging

from server.config.providers import ProviderConfig
from server.domain.errors import ConfigError
from server.persistence.repositories import load_catalog

from .base import BaseProvider, ProviderService
from .llm_provider import LLMProvider

logger = logging.getLogger(__name__)


def _get_model_info(provider_name: str, model_id: str) -> dict:
    """Get full model info from catalog."""
    try:
        catalog = load_catalog()
        models = catalog.get("providers", {}).get(provider_name, {}).get("models", [])
        for m in models:
            if m.get("id") == model_id:
                return m
    except Exception:
        pass
    return {}


def _model_supports_thinking(provider_name: str, model_id: str) -> bool:
    """Check if a model supports thinking via catalog capabilities."""
    info = _get_model_info(provider_name, model_id)
    caps = info.get("model_capabilities", {})
    return bool(caps.get("thinking", False))


def get_model_capabilities(provider_name: str, model_id: str) -> dict:
    """Return model capabilities for runtime use."""
    info = _get_model_info(provider_name, model_id)
    return {
        "thinking": info.get("model_capabilities", {}).get("thinking", False),
        "reasoning": info.get("model_capabilities", {}).get("reasoning", False),
        "function_calling": info.get("model_capabilities", {}).get("function_calling", True),
        "structured_output": info.get("model_capabilities", {}).get("structured_output", False),
        "context_window": info.get("context_window", 128000),
        "speed_tier": info.get("speed_tier", "moderate"),
        "tags": info.get("tags", []),
        "best_for": info.get("best_for", []),
    }


class ProviderRegistry:
    """Registry of provider instances.

    Supports both BaseProvider (legacy) and ProviderService (new typed) interfaces.
    """

    def __init__(self):
        self._providers: dict[str, BaseProvider] = {}

    def register(self, name: str, provider: BaseProvider) -> None:
        self._providers[name] = provider

    def get(self, name: str) -> BaseProvider | None:
        return self._providers.get(name)

    def require(self, name: str) -> BaseProvider:
        provider = self.get(name)
        if provider is None:
            raise ConfigError(
                f"Provider '{name}' not registered. Available: {list(self._providers.keys()) or 'none'}"
            )
        return provider

    def get_typed(self, name: str) -> ProviderService | None:
        """Get provider as typed ProviderService if it implements it."""
        provider = self._providers.get(name)
        if isinstance(provider, ProviderService):
            return provider
        return None

    def require_typed(self, name: str) -> ProviderService:
        """Require provider as typed ProviderService."""
        provider = self.get_typed(name)
        if provider is None:
            raise ConfigError(f"Provider '{name}' does not implement ProviderService")
        return provider

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

    def list_typed(self) -> dict[str, ProviderService]:
        """List all providers that implement ProviderService."""
        return {name: p for name, p in self._providers.items() if isinstance(p, ProviderService)}

    @classmethod
    def from_config(
        cls,
        providers_config: dict[str, ProviderConfig],
        active_provider: str,
    ) -> ProviderRegistry:
        """Create registry from ProviderConfig dict (backward compatible).

        Registers every *configured* provider (one with a model set), not only
        the active one. This lets the backend serve any provider the TUI selects
        without depending on the active provider being swapped in on every switch.
        The active provider remains the default for RPCs that don't name one.
        """
        registry = cls()
        for name, config in providers_config.items():
            if not config.model or not config.model.strip():
                continue
            try:
                catalog_thinking = _model_supports_thinking(name, config.model)
                provider = LLMProvider(
                    name=name,
                    api_key=config.api_key,
                    base_url=config.base_url,
                    model=config.model,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                    enable_thinking=getattr(config, "enable_thinking", False) or catalog_thinking,
                    reasoning_budget=getattr(config, "reasoning_budget", None),
                )
                registry.register(name, provider)
            except Exception as e:
                logger.warning("Skipping provider '%s' in registry: %s", name, e)
        return registry
