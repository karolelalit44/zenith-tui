"""Layered configuration loader.

Precedence (highest wins):
  1. CLI / constructor overrides  — passed directly to ``AppSettings(...)``.
  2. environment variables        — ``ZENITH_*`` scalars plus ``ZENITH_HOOKS`` JSON.
  3. config file (storage)        — provider/model catalog + ``user_profile.json``
                                   (active provider, api keys, per-provider settings).
  4. code defaults                — ``AppSettings.field_defaults`` / ``constants.py``.

``load_config()`` merges the storage file (3) with env overrides (2) into a typed
``AppSettings`` object.  Callers that need CLI/constructor precedence pass values
directly to the returned ``AppSettings`` (or ``model_copy(update=...)``) so their
override beats everything below it.
"""

import json
import logging
import os
from pathlib import Path

from . import environment  # noqa: F401
from .constants import DEFAULT_LLM_MAX_TOKENS, DEFAULT_LLM_TEMPERATURE
from .settings import AppSettings

logger = logging.getLogger(__name__)
_validated_once = False


def _load_catalog():
    from server.storage import load_catalog

    return load_catalog()


def providers_requiring_key() -> set[str]:
    catalog = _load_catalog()
    return {pid for pid, p in catalog["providers"].items() if p.get("requires_api_key", True)}


def parse_hooks_env(raw: str) -> dict | None:
    if not raw or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Invalid ZENITH_HOOKS JSON — hooks disabled: %s", e)
        return None
    if not isinstance(parsed, dict):
        logger.warning("ZENITH_HOOKS must be a JSON object — hooks disabled")
        return None
    hooks: dict = {}
    for key in ("pre_tool_use", "post_tool_use", "session_start"):
        val = parsed.get(key)
        if isinstance(val, list):
            hooks[key] = [str(c) for c in val]
    if "timeout" in parsed:
        try:
            hooks["timeout"] = int(parsed["timeout"])
        except (TypeError, ValueError):
            pass
    return hooks or None


def _environment_overrides() -> dict:
    """Return validated runtime scalar overrides from the current environment."""
    data: dict = {}
    string_fields = {
        "ZENITH_LOG_LEVEL": "log_level",
        "ZENITH_EXPLORE_DELEGATION": "explore_delegation",
    }
    list_fields = {
        "ZENITH_ALLOWED_WS_ORIGINS": "allowed_ws_origins",
    }
    integer_fields = {
        "ZENITH_MAX_CONTEXT_TOKENS": "max_context_tokens",
        "ZENITH_EXPLORE_TOKEN_BUDGET": "explore_token_budget",
    }
    float_fields = {
        "ZENITH_SUMMARY_THRESHOLD": "summary_threshold",
        "ZENITH_CONTEXT_COMPACTION_THRESHOLD": "context_compaction_threshold",
    }
    boolean_fields = {
        "ZENITH_ALLOW_EMPTY_WS_ORIGIN": "allow_empty_ws_origin",
        "ZENITH_ASYNC_SUMMARY_ENABLED": "async_summary_enabled",
    }

    for env_name, field_name in string_fields.items():
        raw = os.environ.get(env_name, "").strip()
        if raw:
            data[field_name] = raw
    for env_name, field_name in list_fields.items():
        raw = os.environ.get(env_name, "").strip()
        if raw:
            values = [item.strip() for item in raw.split(",") if item.strip()]
            if values:
                data[field_name] = values
    for env_name, field_name in integer_fields.items():
        raw = os.environ.get(env_name, "").strip()
        if not raw:
            continue
        try:
            data[field_name] = int(raw)
        except ValueError:
            logger.warning("Invalid %s value %r - ignored", env_name, raw)
    for env_name, field_name in float_fields.items():
        raw = os.environ.get(env_name, "").strip()
        if not raw:
            continue
        try:
            data[field_name] = float(raw)
        except ValueError:
            logger.warning("Invalid %s value %r - ignored", env_name, raw)
    for env_name, field_name in boolean_fields.items():
        raw = os.environ.get(env_name, "").strip().lower()
        if not raw:
            continue
        if raw in {"1", "true", "yes", "on"}:
            data[field_name] = True
        elif raw in {"0", "false", "no", "off"}:
            data[field_name] = False
        else:
            logger.warning("Invalid %s value %r - ignored", env_name, raw)

    bash_timeout = os.environ.get("ZENITH_BASH_TIMEOUT", "").strip()
    if bash_timeout:
        try:
            data["tools"] = {"max_bash_timeout": int(bash_timeout)}
        except ValueError:
            logger.warning("Invalid ZENITH_BASH_TIMEOUT value %r - ignored", bash_timeout)
    return data


def load_config(workspace_root: str = ".") -> AppSettings:
    data: dict = {"workspace_root": workspace_root}

    from server.storage import StorageHome, ensure_materialized, resolve_home
    from server.storage.provider_config import read_active_provider, read_providers

    home = StorageHome(resolve_home())
    ensure_materialized(home)
    data["home_dir"] = str(home.root)

    providers_dict: dict[str, dict] = {}
    try:
        active = read_active_provider(home)
        if active:
            data["active_provider"] = active
        stored = read_providers(home)
        providers_dict.update(stored)
    except Exception as e:
        logger.warning("Could not read provider config from storage home '%s': %s", home.root, e)

    catalog = _load_catalog()
    catalog_providers = catalog.get("providers", {})
    # API keys resolve exclusively from user_profile.json (decision D5);
    # environment-variable fallbacks were removed with the database.
    for pid, p_info in catalog_providers.items():
        if pid not in providers_dict:
            entry = {
                "api_key": "",
                "model": "",
                "base_url": p_info.get("base_url"),
                "max_tokens": DEFAULT_LLM_MAX_TOKENS,
                "temperature": DEFAULT_LLM_TEMPERATURE,
                "is_active": pid == data.get("active_provider"),
            }
            providers_dict[pid] = entry
        else:
            entry = providers_dict[pid]
            if not entry.get("base_url"):
                entry["base_url"] = p_info.get("base_url")

    data["providers"] = providers_dict
    data.update(_environment_overrides())
    hooks_raw = os.environ.get("ZENITH_HOOKS", "").strip()
    if hooks_raw:
        hooks_cfg = parse_hooks_env(hooks_raw)
        if hooks_cfg:
            data["hooks"] = hooks_cfg
    settings = AppSettings(**data)
    _validate_config(settings)
    return settings


def _validate_config(settings: AppSettings) -> None:
    global _validated_once
    if _validated_once:
        return
    _validated_once = True
    warnings: list[str] = []
    providers = settings.providers or {}
    has_any_key = False
    requiring_key = providers_requiring_key()
    for name, cfg in providers.items():
        if name in requiring_key:
            key = getattr(cfg, "api_key", None) or ""
            if key.strip():
                has_any_key = True
                break
            warnings.append(f"Provider '{name}' is configured but missing a valid API key.")
    if not has_any_key and (not any(getattr(cfg, "api_key", None) for cfg in providers.values())):
        warnings.append(
            "No provider API keys found in user_profile.json. Configure at least one provider via setup wizard."
        )
    catalog = _load_catalog()
    if settings.active_provider not in providers and settings.active_provider not in catalog.get(
        "providers", {}
    ):
        warnings.append(
            f"Active provider '{settings.active_provider}' is not in the configured providers list {list(providers.keys()) or '[]'}. Set an active provider via the setup wizard."
        )
    workspace = Path(settings.workspace_root)
    if not workspace.exists():
        warnings.append(f"Workspace root '{settings.workspace_root}' does not exist.")
    home_dir = Path(settings.home_dir)
    if not home_dir.exists():
        try:
            home_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            warnings.append(f"Cannot create storage home '{home_dir}': {e}")
    for warning in warnings:
        logger.warning("Config: %s", warning)
    _warn_on_legacy_database(settings)


def _warn_on_legacy_database(settings: AppSettings) -> None:
    """Point out a pre-migration SQLite file that is intentionally unused."""
    candidates = (
        Path.cwd() / "data" / "zenith.db",
        Path(settings.workspace_root) / "data" / "zenith.db",
        Path(settings.home_dir) / "zenith.db",
    )
    for candidate in candidates:
        if candidate.exists():
            logger.warning(
                "Found legacy database %s — it is NO LONGER USED. All state now "
                "lives under the storage home '%s'. The old sessions/history in "
                "the database are intentionally not migrated.",
                candidate,
                settings.home_dir,
            )


def create_default_config(workspace_root: str = ".") -> Path:
    from server.storage import StorageHome, ensure_materialized, resolve_home

    home = StorageHome(resolve_home())
    ensure_materialized(home)
    return home.root
