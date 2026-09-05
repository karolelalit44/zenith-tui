from __future__ import annotations

import logging

from server.config.constants import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_LLM_TEMPERATURE,
    default_max_tokens_for_context,
)
from server.config.providers import ProviderConfig
from server.domain.errors import ConfigError
from server.storage import load_catalog

from .base import BaseProvider
from .llm_provider import LLMProvider

logger = logging.getLogger(__name__)


def _get_model_info(provider_name: str, model_id: str) -> dict:
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
    info = _get_model_info(provider_name, model_id)
    caps = info.get("model_capabilities", {})
    return bool(caps.get("thinking", False))


def _resolve_model_defaults(provider_name: str, model_id: str) -> dict[str, float | int]:
    info = _get_model_info(provider_name, model_id)
    ctx = info.get("context_window", DEFAULT_CONTEXT_WINDOW)
    max_tokens = info.get("max_output_tokens")
    if max_tokens is None:
        max_tokens = default_max_tokens_for_context(ctx)
    temperature = info.get("default_temperature", DEFAULT_LLM_TEMPERATURE)
    return {"max_tokens": int(max_tokens), "temperature": float(temperature)}


class ProviderRegistry:
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

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

    def update_provider(self, name: str, config: ProviderConfig) -> BaseProvider | None:
        """Re-instantiate a single provider in-place without touching others."""
        if not config.model or not config.model.strip():
            self._providers.pop(name, None)
            return None
        try:
            catalog_thinking = _model_supports_thinking(name, config.model)
            model_defaults = _resolve_model_defaults(name, config.model)
            provider = LLMProvider(
                name=name,
                api_key=config.api_key,
                base_url=config.base_url,
                model=config.model,
                max_tokens=int(model_defaults["max_tokens"]),
                temperature=model_defaults["temperature"],
                enable_thinking=getattr(config, "enable_thinking", False) or catalog_thinking,
                reasoning_budget=getattr(config, "reasoning_budget", None),
                reasoning_effort=getattr(config, "reasoning_effort", None),
            )
            self._providers[name] = provider
            return provider
        except Exception as e:
            logger.warning("Failed to update provider '%s': %s", name, e)
            return self._providers.get(name)

    def remove_provider(self, name: str) -> None:
        """Remove a provider from the registry."""
        self._providers.pop(name, None)

    @classmethod
    def from_config(
        cls, providers_config: dict[str, ProviderConfig], active_provider: str
    ) -> ProviderRegistry:
        registry = cls()
        for name, config in providers_config.items():
            if not config.model or not config.model.strip():
                continue
            try:
                catalog_thinking = _model_supports_thinking(name, config.model)
                model_defaults = _resolve_model_defaults(name, config.model)
                provider = LLMProvider(
                    name=name,
                    api_key=config.api_key,
                    base_url=config.base_url,
                    model=config.model,
                    max_tokens=int(model_defaults["max_tokens"]),
                    temperature=model_defaults["temperature"],
                    enable_thinking=getattr(config, "enable_thinking", False) or catalog_thinking,
                    reasoning_budget=getattr(config, "reasoning_budget", None),
                    reasoning_effort=getattr(config, "reasoning_effort", None),
                )
                registry.register(name, provider)
            except Exception as e:
                logger.warning("Skipping provider '%s' in registry: %s", name, e)
        return registry
