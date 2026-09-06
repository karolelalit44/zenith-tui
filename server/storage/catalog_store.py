"""zenith_catalog.json — the provider/model catalog in a single file.

The catalog lives in ONE JSON document whose ``providers`` list matches the
``builtin_seed.PROVIDERS`` shape (each provider object carries its own nested
``models`` array). This replaces the legacy two-file split
(``providers.json`` + ``models.json``).

Builtin rows refresh when ``SEED_VERSION`` increases; user rows are never
touched by upgrades. Secrets are structurally rejected here (decision D5).
Runtime state (keys, active ids, per-provider settings) belongs in
``user_profile.json`` — never in the catalog.
"""

from __future__ import annotations

import copy
import logging
import threading

from . import builtin_seed
from .atomic import read_json, write_json_atomic
from .paths import StorageHome

logger = logging.getLogger(__name__)

CATALOG_VERSION = 2

_lock = threading.Lock()
_cache: dict[str, dict] = {}

_FORBIDDEN_KEYS = {"apiKey", "apiKeyValue", "api_key", "secret", "token"}


class CatalogValidationError(ValueError):
    pass


def _validate_no_secrets(entry: dict, where: str) -> None:
    for key in entry:
        if key.lower() in _FORBIDDEN_KEYS:
            raise CatalogValidationError(
                f"{where}: secret-like field {key!r} is not allowed in catalog files"
            )


def _catalog_document() -> dict:
    """Fresh single-file catalog — a deep copy of the builtin seed."""
    return {
        "version": CATALOG_VERSION,
        "seedVersion": builtin_seed.SEED_VERSION,
        "providers": copy.deepcopy(builtin_seed.PROVIDERS),
    }


# ── reads ─────────────────────────────────────────────────────────────


def read_catalog_doc(home: StorageHome) -> dict:
    """The full catalog document: ``{version, seedVersion, providers: [...]}``."""
    doc = read_json(home.catalog_path, None)
    if not isinstance(doc, dict) or not isinstance(doc.get("providers"), list):
        return {
            "version": CATALOG_VERSION,
            "seedVersion": builtin_seed.SEED_VERSION,
            "providers": [],
        }
    return doc


def read_providers(home: StorageHome) -> dict[str, dict]:
    """All provider entries keyed by id (each with a nested ``models`` list)."""
    providers = read_catalog_doc(home).get("providers", [])
    return {str(p["id"]): p for p in providers if isinstance(p, dict) and p.get("id")}


def read_model_entries(home: StorageHome) -> dict[str, dict]:
    """Every model flattened across providers, keyed by composite ``key``."""
    out: dict[str, dict] = {}
    for provider in read_catalog_doc(home).get("providers", []):
        if not isinstance(provider, dict):
            continue
        pid = str(provider.get("id", ""))
        for model in provider.get("models", []):
            if not isinstance(model, dict):
                continue
            key = str(model.get("key") or "")
            if not key and model.get("id"):
                key = f"{pid}/{model['id']}"
            if key:
                out[key] = model
    return out


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
        built = _build_runtime_catalog(home or StorageHome(root_key))
        _cache[root_key] = built
        return built


def _build_runtime_catalog(home: StorageHome) -> dict:
    doc = read_catalog_doc(home)
    providers: dict[str, dict] = {}
    for entry in sorted(
        (p for p in doc.get("providers", []) if isinstance(p, dict)),
        key=lambda p: (p.get("sortOrder", 99), str(p.get("id", ""))),
    ):
        pid = str(entry.get("id", ""))
        if not pid:
            continue
        default_model = str(entry.get("defaultModelId") or "")
        prefix = f"{pid}/"
        default_model = default_model.removeprefix(prefix)
        models = sorted(
            (_model_runtime_shape(m) for m in entry.get("models", []) if isinstance(m, dict)),
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
            "_catalog_version": CATALOG_VERSION,
        }
    return {"version": 1, "providers": providers}


def _model_runtime_shape(entry: dict) -> dict:
    shape = {
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
    max_out = entry.get("maxOutputTokens") or entry.get("max_output_tokens")
    if max_out:
        shape["max_output_tokens"] = int(max_out)
    return shape


def _write(home: StorageHome, providers: list[dict]) -> None:
    write_json_atomic(
        home.catalog_path,
        {
            "version": CATALOG_VERSION,
            "seedVersion": builtin_seed.SEED_VERSION,
            "providers": providers,
        },
    )


# ── materialization / migration ────────────────────────────────────────


def _legacy_layout_exists(home: StorageHome) -> bool:
    return (
        home.root.joinpath("providers.json").exists() or home.root.joinpath("models.json").exists()
    )


def _migrate_legacy(home: StorageHome) -> dict | None:
    """Merge legacy providers.json + models.json into the single nested doc.

    Returns ``None`` when there is nothing worth migrating.
    """
    pdoc = read_json(home.root.joinpath("providers.json"), None)
    mdoc = read_json(home.root.joinpath("models.json"), None)
    if not isinstance(pdoc, dict) or not isinstance(pdoc.get("providers"), list):
        return None
    models_by_provider: dict[str, list[dict]] = {}
    if isinstance(mdoc, dict):
        for entry in (mdoc.get("models") or {}).values():
            if not isinstance(entry, dict):
                continue
            models_by_provider.setdefault(str(entry.get("providerId", "")), []).append(entry)
    providers: list[dict] = []
    for entry in pdoc["providers"]:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        merged = dict(entry)
        pid = entry["id"]
        merged.setdefault("models", models_by_provider.get(pid, []))
        providers.append(merged)
    # orphan user models (no matching provider row) => a synthetic provider
    for pid, models in models_by_provider.items():
        if not models or any(p.get("id") == pid for p in providers):
            continue
        providers.append({"id": pid, "name": pid.title(), "source": "user", "models": models})
    return {
        "version": CATALOG_VERSION,
        "seedVersion": pdoc.get("seedVersion", 0),
        "providers": providers,
    }


def ensure_materialized(home: StorageHome) -> None:
    """Create zenith_catalog.json if missing (migrating the legacy layout);
    refresh builtin rows when the seed version advanced."""
    home.ensure_layout()
    if home.catalog_path.exists():
        _refresh_seed(home)
        _purge_legacy_files(home)  # stale superseded files from a partial migration
    elif _legacy_layout_exists(home):
        migrated = _migrate_legacy(home)
        if migrated is not None:
            write_json_atomic(home.catalog_path, migrated)
            _purge_legacy_files(home)
            logger.info("Migrated legacy providers.json/models.json -> zenith_catalog.json")
        else:
            write_json_atomic(home.catalog_path, _catalog_document())
    else:
        write_json_atomic(home.catalog_path, _catalog_document())
    invalidate_catalog_cache()


def _purge_legacy_files(home: StorageHome) -> None:
    for name in ("providers.json", "models.json", "providers.json.bak", "models.json.bak"):
        path = home.root.joinpath(name)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove legacy catalog file %s", path)


def _refresh_seed(home: StorageHome) -> None:
    doc = read_catalog_doc(home)
    stored_version = doc.get("seedVersion", 0)
    if stored_version >= builtin_seed.SEED_VERSION:
        return
    seed_by_id = {p["id"]: copy.deepcopy(p) for p in builtin_seed.PROVIDERS}
    providers: list[dict] = []
    for provider in doc.get("providers", []):
        if not isinstance(provider, dict) or not provider.get("id"):
            continue
        pid = str(provider["id"])
        if pid not in seed_by_id:
            providers.append(provider)  # non-builtin user provider row
            continue
        fresh = seed_by_id.pop(pid)
        if provider.get("source", "builtin") == "user":
            providers.append(provider)  # user-edited builtin is authoritative
            continue
        seed_map: dict[str, dict] = {}
        for m in fresh.get("models", []):
            if isinstance(m, dict) and m.get("key"):
                seed_map[m["key"]] = m
        for model in provider.get("models", []):
            if not isinstance(model, dict):
                continue
            if model.get("source", "builtin") == "builtin":
                continue  # unedited builtin row — refreshed by the seed
            key = model.get("key")
            if not key and model.get("id"):
                key = f"{pid}/{model['id']}"
            if key:
                seed_map[key] = model  # user-edited builtin or user-added model
        fresh["models"] = list(seed_map.values())
        providers.append(fresh)
    providers.extend(seed_by_id.values())  # newly introduced builtin providers
    providers.sort(key=lambda p: (p.get("sortOrder", 99), str(p.get("id", ""))))
    _write(home, providers)
    logger.info("Refreshed builtin catalog to seed v%s", builtin_seed.SEED_VERSION)


# ── writes ────────────────────────────────────────────────────────────


def upsert_provider(home: StorageHome, entry: dict) -> None:
    _validate_no_secrets(entry, f"provider {entry.get('id', '?')}")
    providers = read_catalog_doc(home).get("providers", [])
    pid = entry.get("id")
    out: list[dict] = []
    replaced = False
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
    _write(home, out)
    invalidate_catalog_cache()


def upsert_model(home: StorageHome, entry: dict) -> str:
    _validate_no_secrets(entry, f"model {entry.get('key', entry.get('id', '?'))}")
    providers = read_catalog_doc(home).get("providers", [])
    key = entry.get("key") or f"{entry.get('providerId')}/{entry.get('id')}"
    fresh = dict(entry)
    fresh["key"] = key
    # Runtime edits are user-authoritative (survive seed refreshes).
    fresh["source"] = "user"
    provider_id = entry.get("providerId") or key.split("/", 1)[0]
    provider = next((p for p in providers if p.get("id") == provider_id), None)
    if provider is None:
        provider = {
            "id": provider_id,
            "name": str(provider_id).title(),
            "source": "user",
            "models": [],
        }
        providers.append(provider)
    models = provider.setdefault("models", [])
    matched = False
    for i, model in enumerate(models):
        if isinstance(model, dict) and (
            model.get("key") == key or model.get("id") == entry.get("id")
        ):
            models[i] = fresh
            matched = True
            break
    if not matched:
        models.append(fresh)
    _write(home, providers)
    invalidate_catalog_cache()
    return key
