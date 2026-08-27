"""Compatibility adapter exposing the legacy ``load_catalog()`` shape.

Downstream consumers (llm_provider, registry, validation, token_counter,
agents/*) were written against the SQLite catalog reader. This module
produces the exact same dict shape from ``providers.json`` /
``models.json`` so those consumers only need an import swap.
"""

from __future__ import annotations

import threading

from .atomic import read_json
from .paths import StorageHome

EMPTY_CATALOG: dict = {"version": 1, "providers": {}}

_lock = threading.Lock()
_cache: dict[str, dict] = {}


def invalidate_catalog_cache() -> None:
    with _lock:
        _cache.clear()


def load_catalog(home: StorageHome | None = None) -> dict:
    from .paths import resolve_home

    root_key = str((home or StorageHome(resolve_home())).root)
    with _lock:
        cached = _cache.get(root_key)
        if cached is not None:
            return cached
        built = _build(StorageHome(root_key))
        _cache[root_key] = built
        return built


def _build(home: StorageHome) -> dict:
    pdoc = read_json(home.providers_path, None)
    mdoc = read_json(home.models_path, None)
    if not isinstance(pdoc, dict) or not isinstance(pdoc.get("providers"), list):
        return dict(EMPTY_CATALOG)
    models_by_provider: dict[str, list[dict]] = {}
    if isinstance(mdoc, dict):
        for entry in (mdoc.get("models") or {}).values():
            if not isinstance(entry, dict):
                continue
            models_by_provider.setdefault(str(entry.get("providerId")), []).append(entry)

    providers: dict[str, dict] = {}
    for entry in sorted(
        (p for p in pdoc["providers"] if isinstance(p, dict)),
        key=lambda p: (p.get("sortOrder", 99), str(p.get("id", ""))),
    ):
        pid = str(entry.get("id", ""))
        if not pid:
            continue
        default_model = str(entry.get("defaultModelId") or "")
        prefix = f"{pid}/"
        default_model = default_model.removeprefix(prefix)
        models = sorted(
            (_model_runtime_shape(m) for m in models_by_provider.get(pid, [])),
            key=lambda m: (not m["is_default"], m["name"]),
        )
        providers[pid] = {
            "id": pid,
            "name": entry.get("name", pid),
            "description": entry.get("description", ""),
            "adapter": entry.get("adapter", "openai_compat"),
            "litellm_prefix": entry.get("litellmPrefix", ""),
            "default_model": default_model,
            "base_url": entry.get("baseUrl", ""),
            "api_key_prefix": entry.get("apiKeyPrefixHint"),
            "requires_api_key": bool(entry.get("requiresApiKey", True)),
            "swatch": entry.get("swatch", []),
            "capabilities": entry.get("capabilities", {}),
            "config_fields": entry.get("configFields", []),
            "env_keys": entry.get("apiKeyEnv", []),
            "is_popular": bool(entry.get("isPopular", False)),
            "base_url_style": entry.get("baseStyle", ""),
            "supports_prompt_caching": bool(entry.get("supportsPromptCaching", False)),
            "supports_thinking_headers": bool(entry.get("supportsThinkingHeaders", False)),
            "custom_flow": bool(entry.get("customFlow", False)),
            "rate_limit": entry.get("rateLimit", {}),
            "models": models,
        }
    return {"version": 1, "providers": providers}


def _model_runtime_shape(entry: dict) -> dict:
    return {
        "id": entry.get("id", ""),
        "name": entry.get("name", ""),
        "description": entry.get("description", ""),
        "context_window": int(entry.get("contextWindow", 128000)),
        "parameters": entry.get("parameters"),
        "architecture": entry.get("architecture"),
        "input_modalities": entry.get("inputModalities", []),
        "output_modalities": entry.get("outputModalities", []),
        "tags": entry.get("tags", []),
        "model_capabilities": entry.get("capabilities", {}),
        "speed_tier": entry.get("speedTier", ""),
        "best_for": entry.get("bestFor", []),
        "pricing": entry.get("pricing", {}),
        "is_default": bool(entry.get("isDefault", False)),
        "tokenizer": entry.get("tokenizer", ""),
        "prompt_tier": entry.get("promptTier", ""),
    }
