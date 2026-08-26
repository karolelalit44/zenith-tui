"""File-backed provider configuration — replaces provider_config_repo.

State split:
- ``providers.json``  : catalog definitions (no secrets, no user credentials)
- ``user_profile.json``: apiKeys map + per-provider settings + active ids
- ``models.json``     : all models (builtin seed rows + user-added rows)

Function signatures mirror the legacy repo so call sites only swap the
import and pass a :class:`StorageHome` instead of ``db_path``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .catalog_compat import load_catalog
from .catalog_store import upsert_model
from .paths import StorageHome
from .profile_store import (
    PROFILE_LOCK,
    get_api_key,
    load_profile,
    mask_api_key,
    save_profile,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7



def read_active_provider(home: StorageHome) -> str | None:
    profile = load_profile(home)
    value = profile.get("activeProviderId", "")
    return value if value else None


def _settings_for(profile: dict, pid: str) -> dict:
    settings = profile.get("providerSettings") or {}
    raw = settings.get(pid)
    return raw if isinstance(raw, dict) else {}


def read_providers(home: StorageHome) -> dict[str, dict[str, Any]]:
    """Internal shape with the RAW api key (never exposed over HTTP)."""
    profile = load_profile(home)
    active = profile.get("activeProviderId", "")
    result: dict[str, dict[str, Any]] = {}
    pids = set((profile.get("apiKeys") or {}).keys()) | set(
        (profile.get("providerSettings") or {}).keys()
    )
    for pid in sorted(pids):
        cfg = _settings_for(profile, pid)
        result[pid] = {
            "api_key": get_api_key(profile, pid),
            "model": str(cfg.get("model") or ""),
            "base_url": str(cfg.get("baseUrl") or ""),
            "max_tokens": int(cfg.get("maxTokens", DEFAULT_MAX_TOKENS)),
            "temperature": float(cfg.get("temperature", DEFAULT_TEMPERATURE)),
            "is_active": pid == active,
        }
    return result


def read_provider_config_full(
    home: StorageHome,
) -> tuple[str, dict[str, dict[str, Any]]]:
    """Masked, HTTP-safe view merged with catalog metadata."""
    profile = load_profile(home)
    active = profile.get("activeProviderId", "")
    catalog = load_catalog(home)
    models_by_provider: dict[str, dict[str, dict]] = {}
    for pid, pdata in catalog.get("providers", {}).items():
        models_by_provider[pid] = {m["id"]: m for m in pdata.get("models", [])}
    stored_models = _stored_models_for(home)

    result: dict[str, dict[str, Any]] = {}
    pids = (
        set((profile.get("apiKeys") or {}).keys())
        | set((profile.get("providerSettings") or {}).keys())
        | set(catalog.get("providers", {}).keys())
    )
    for pid in sorted(pids):
        cat_entry = catalog.get("providers", {}).get(pid, {})
        cfg = _settings_for(profile, pid)
        key = get_api_key(profile, pid)
        enriched = []
        for m in stored_models.get(pid, []):
            c = models_by_provider.get(pid, {}).get(m["id"], {})
            enriched.append(
                {
                    "id": m["id"],
                    "name": m["name"],
                    "context_window": m["context_window"],
                    "description": m["description"],
                    "is_default": m["is_default"],
                    "parameters": c.get("parameters"),
                    "architecture": c.get("architecture"),
                    "input_modalities": c.get("input_modalities"),
                    "output_modalities": c.get("output_modalities"),
                    "tags": c.get("tags"),
                    "model_capabilities": c.get("model_capabilities"),
                    "speed_tier": c.get("speed_tier"),
                    "best_for": c.get("best_for"),
                }
            )
        result[pid] = {
            "id": pid,
            "name": cat_entry.get("name") or pid.title(),
            "description": cat_entry.get("description", ""),
            "api_key": mask_api_key(key),
            "has_api_key": bool(key.strip()),
            "api_key_masked": mask_api_key(key),
            "model": str(cfg.get("model") or ""),
            "base_url": str(cfg.get("baseUrl") or cat_entry.get("base_url") or ""),
            "max_tokens": int(cfg.get("maxTokens", DEFAULT_MAX_TOKENS)),
            "temperature": float(cfg.get("temperature", DEFAULT_TEMPERATURE)),
            "is_active": pid == active,
            "swatch_json": _json_dump(cat_entry.get("swatch", [])),
            "adapter_type": cat_entry.get("adapter", "openai_compat"),
            "capabilities_json": _json_dump(cat_entry.get("capabilities", {})),
            "api_key_prefix": cat_entry.get("api_key_prefix"),
            "updated_at": cfg.get("updatedAt"),
            "models": enriched,
            "swatch": cat_entry.get("swatch", []),
        }
    return (active, result)


def save_provider_config(
    home: StorageHome,
    provider: str,
    api_key: str = "",
    model: str = "",
    base_url: str = "",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    set_active: bool = True,
) -> None:
    # Full read-modify-write under the process-wide profile lock: this runs
    # on the event loop while preference writes may run in threadpool
    # threads; without the lock, concurrent whole-document saves could
    # drop each other's keys/settings.
    with PROFILE_LOCK:
        profile = load_profile(home)
        existing_cfg = _settings_for(profile, provider)
        new_key = get_api_key(profile, provider)
        if api_key.strip():
            new_key = api_key.strip()
        keys = profile.setdefault("apiKeys", {})
        if new_key:
            keys[provider] = new_key
        else:
            keys.pop(provider, None)

        settings = profile.setdefault("providerSettings", {})
        merged = dict(existing_cfg)
        merged.update(
            {
                "model": model.strip() or str(existing_cfg.get("model") or ""),
                "baseUrl": base_url.strip() or str(existing_cfg.get("baseUrl") or ""),
                "maxTokens": int(max_tokens),
                "temperature": float(temperature),
                "updatedAt": datetime.now().isoformat(),
            }
        )
        settings[provider] = merged
        if set_active:
            profile["activeProviderId"] = provider
        save_profile(home, profile)
    logger.info(
        "Saved provider config '%s' (active=%s)", provider, set_active
    )


def upsert_provider_models(
    home: StorageHome, provider: str, models: list[dict]
) -> None:
    """Persist user-added/curated models for a provider into models.json."""
    for m in models or []:
        mid = str(m.get("id") or "").strip()
        if not mid:
            continue
        entry = {
            "providerId": provider,
            "id": mid,
            "name": str(m.get("name") or mid),
            "description": str(m.get("description") or ""),
            "contextWindow": int(m.get("context_window") or 128000),
            "isDefault": bool(m.get("is_default", False)),
            "source": "user",
        }
        try:
            upsert_model(home, entry)
        except Exception as e:
            logger.warning("upsert_provider_models: failed for %s/%s: %s",
                           provider, mid, e)


def _stored_models_for(home: StorageHome) -> dict[str, list[dict]]:
    from .catalog_store import read_model_entries

    out: dict[str, list[dict]] = {}
    for entry in read_model_entries(home).values():
        pid = str(entry.get("providerId"))
        out.setdefault(pid, []).append(
            {
                "id": str(entry.get("id", "")),
                "name": str(entry.get("name", "")),
                "context_window": int(entry.get("contextWindow", 128000)),
                "description": str(entry.get("description", "")),
                "is_default": bool(entry.get("isDefault", False)),
            }
        )
    return out


# ── model-store (current/recent/favorite) lives in profile.preferences ──


def _json_dump(value: Any) -> str:
    import json

    return json.dumps(value if value is not None else [])
