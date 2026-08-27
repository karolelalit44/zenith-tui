"""providers.json + models.json — the provider/model catalog.

Materialized from :mod:`server.storage.builtin_seed` on first boot.
Builtin rows refresh when ``SEED_VERSION`` increases; user rows are never
touched by upgrades. Secrets are structurally rejected here (decision D5).
"""

from __future__ import annotations

import logging

from . import builtin_seed
from .atomic import read_json, write_json_atomic
from .catalog_compat import invalidate_catalog_cache
from .paths import StorageHome

logger = logging.getLogger(__name__)

CATALOG_VERSION = 1

_FORBIDDEN_KEYS = {"apiKey", "apiKeyValue", "api_key", "secret", "token"}


class CatalogValidationError(ValueError):
    pass


def _validate_no_secrets(entry: dict, where: str) -> None:
    for key in entry:
        if key.lower() in _FORBIDDEN_KEYS:
            raise CatalogValidationError(
                f"{where}: secret-like field {key!r} is not allowed in catalog files"
            )


def _builtin_providers_document() -> dict:
    return {
        "version": CATALOG_VERSION,
        "seedVersion": builtin_seed.SEED_VERSION,
        "providers": [dict(p) for p in builtin_seed.PROVIDERS],
    }


def _builtin_models_document() -> dict:
    return {
        "version": CATALOG_VERSION,
        "seedVersion": builtin_seed.SEED_VERSION,
        "defaults": dict(builtin_seed.DEFAULTS),
        "models": {m["key"]: dict(m) for m in builtin_seed._MODELS},
    }


def ensure_materialized(home: StorageHome) -> None:
    """Create providers.json/models.json if missing; refresh builtin rows
    when the seed version advanced."""
    home.ensure_layout()
    _ensure_providers(home)
    _ensure_models(home)
    # Seed refresh rewrote catalog files: consumers must not keep serving
    # a cached pre-refresh view.
    invalidate_catalog_cache()


def _ensure_providers(home: StorageHome) -> None:
    doc = read_json(home.providers_path, None)
    if not isinstance(doc, dict) or not isinstance(doc.get("providers"), list):
        write_json_atomic(home.providers_path, _builtin_providers_document())
        return
    stored_version = doc.get("seedVersion", 0)
    if stored_version >= builtin_seed.SEED_VERSION:
        return
    builtin_by_id = {p["id"]: p for p in builtin_seed.PROVIDERS}
    kept: list[dict] = []
    for entry in doc["providers"]:
        if not isinstance(entry, dict):
            continue
        pid = entry.get("id")
        if pid in builtin_by_id and entry.get("source", "builtin") == "builtin":
            continue  # stale unmodified builtin row — re-added fresh below
        kept.append(entry)  # user rows AND user-edited builtin rows survive
    for pid, fresh in builtin_by_id.items():
        existing = next((e for e in kept if e.get("id") == pid), None)
        if existing is not None:
            continue  # user-modified builtin is authoritative — no duplicate
        kept.append(dict(fresh))
    new_doc = {
        "version": CATALOG_VERSION,
        "seedVersion": builtin_seed.SEED_VERSION,
        "providers": kept,
    }
    write_json_atomic(home.providers_path, new_doc)
    logger.info("Refreshed builtin providers to seed v%s", builtin_seed.SEED_VERSION)


def _ensure_models(home: StorageHome) -> None:
    doc = read_json(home.models_path, None)
    if not isinstance(doc, dict) or not isinstance(doc.get("models"), dict):
        write_json_atomic(home.models_path, _builtin_models_document())
        return
    stored_version = doc.get("seedVersion", 0)
    if stored_version >= builtin_seed.SEED_VERSION:
        return
    models = {
        key: entry
        for key, entry in doc["models"].items()
        if isinstance(entry, dict) and entry.get("source", "builtin") != "builtin"
    }
    for key, fresh in builtin_seed.MODELS_BY_KEY.items():
        existing = models.get(key)
        if existing is not None:
            continue  # user-edited model row (source=user) is authoritative
        models[key] = dict(fresh)
    new_doc = {
        "version": CATALOG_VERSION,
        "seedVersion": builtin_seed.SEED_VERSION,
        "defaults": doc.get("defaults") or dict(builtin_seed.DEFAULTS),
        "models": models,
    }
    write_json_atomic(home.models_path, new_doc)
    logger.info("Refreshed builtin models to seed v%s", builtin_seed.SEED_VERSION)


# ── reads ─────────────────────────────────────────────────────────────


def read_providers(home: StorageHome) -> dict[str, dict]:
    """All provider entries keyed by id, sorted by sortOrder then id."""
    doc = read_json(home.providers_path, None) or {}
    entries = [e for e in doc.get("providers", []) if isinstance(e, dict)]
    entries.sort(key=lambda e: (e.get("sortOrder", 99), str(e.get("id", ""))))
    return {e["id"]: e for e in entries if e.get("id")}


def read_model_entries(home: StorageHome) -> dict[str, dict]:
    doc = read_json(home.models_path, None) or {}
    models = doc.get("models")
    return models if isinstance(models, dict) else {}


def models_for_provider(home: StorageHome, provider_id: str) -> list[dict]:
    entries = [m for m in read_model_entries(home).values() if m.get("providerId") == provider_id]
    entries.sort(key=lambda m: (not m.get("isDefault", False), str(m.get("id", ""))))
    return entries


# ── writes ────────────────────────────────────────────────────────────


def upsert_provider(home: StorageHome, entry: dict) -> None:
    _validate_no_secrets(entry, f"provider {entry.get('id', '?')}")
    doc = read_json(home.providers_path, None)
    if not isinstance(doc, dict) or not isinstance(doc.get("providers"), list):
        doc = _builtin_providers_document()
    providers: list[dict] = [p for p in doc["providers"] if isinstance(p, dict)]
    pid = entry.get("id")
    replaced = False
    out: list[dict] = []
    for existing in providers:
        if existing.get("id") == pid:
            merged = dict(existing)
            merged.update({k: v for k, v in entry.items() if k != "source"})
            # Any runtime write flips the row to user-authoritative so a
            # later seed refresh preserves the edit (matches models).
            merged["source"] = "user"
            out.append(merged)
            replaced = True
        else:
            out.append(existing)
    if not replaced:
        fresh = dict(entry)
        fresh.setdefault("source", "user")
        out.append(fresh)
    write_json_atomic(
        home.providers_path,
        {
            "version": CATALOG_VERSION,
            "seedVersion": doc.get("seedVersion", builtin_seed.SEED_VERSION),
            "providers": out,
        },
    )
    invalidate_catalog_cache()


def delete_provider(home: StorageHome, provider_id: str) -> bool:
    doc = read_json(home.providers_path, None)
    if not isinstance(doc, dict) or not isinstance(doc.get("providers"), list):
        return False
    entry = next((p for p in doc["providers"] if p.get("id") == provider_id), None)
    if entry is None:
        return False
    if entry.get("firstClass"):
        raise CatalogValidationError(
            f"Provider '{provider_id}' is first-class and cannot be deleted"
        )
    remaining = [p for p in doc["providers"] if p.get("id") != provider_id]
    write_json_atomic(
        home.providers_path,
        {
            "version": CATALOG_VERSION,
            "seedVersion": doc.get("seedVersion", builtin_seed.SEED_VERSION),
            "providers": remaining,
        },
    )
    invalidate_catalog_cache()
    return True


def upsert_model(home: StorageHome, entry: dict) -> str:
    _validate_no_secrets(entry, f"model {entry.get('key', entry.get('id', '?'))}")
    doc = read_json(home.models_path, None)
    if not isinstance(doc, dict) or not isinstance(doc.get("models"), dict):
        doc = _builtin_models_document()
    models = dict(doc["models"])
    key = entry.get("key") or f"{entry.get('providerId')}/{entry.get('id')}"
    fresh = dict(entry)
    fresh["key"] = key
    # Runtime edits are user-authoritative (survive seed refreshes).
    fresh["source"] = "user"
    models[key] = fresh
    write_json_atomic(
        home.models_path,
        {
            "version": CATALOG_VERSION,
            "seedVersion": doc.get("seedVersion", builtin_seed.SEED_VERSION),
            "defaults": doc.get("defaults") or dict(builtin_seed.DEFAULTS),
            "models": models,
        },
    )
    invalidate_catalog_cache()
    return key
