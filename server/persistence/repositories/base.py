from __future__ import annotations

import logging

from server.config.constants import DEFAULT_CONTEXT_WINDOW

from ..connection import resolve_db_path

_logger = logging.getLogger(__name__)
_catalog_cache: dict | None = None


def load_catalog(db_path: str | None = None) -> dict:
    global _catalog_cache
    if db_path is None:
        if _catalog_cache is not None:
            return _catalog_cache
        db_path = resolve_db_path()
    from server.persistence.provider_config_repo import read_catalog

    catalog = read_catalog(db_path)
    if db_path == resolve_db_path():
        _catalog_cache = catalog
    return catalog


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _seed_providers_from_catalog(catalog: dict) -> list[dict]:
    providers = []
    for pid, p in catalog["providers"].items():
        providers.append(
            {
                "id": pid,
                "name": p["name"],
                "description": p.get("description", ""),
                "model": p["default_model"],
                "base_url": p["base_url"],
                "adapter": p.get("adapter", "openai_compat"),
                "capabilities": p.get("capabilities", {}),
                "api_key_prefix": p.get("api_key_prefix"),
                "swatch": p.get("swatch", []),
                "is_active": 0,
                "models": [
                    {
                        "id": m["id"],
                        "name": m["name"],
                        "context_window": m.get("context_window", DEFAULT_CONTEXT_WINDOW),
                        "is_default": 1 if m.get("is_default") else 0,
                    }
                    for m in p.get("models", [])
                ],
            }
        )
    return providers
