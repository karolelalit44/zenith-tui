import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from .settings import AppSettings

logger = logging.getLogger(__name__)
_validated_once = False


def _load_catalog():
    from server.storage.catalog_compat import load_catalog

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


def load_config(workspace_root: str = ".") -> AppSettings:
    load_dotenv()
    data: dict = {}

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
                "max_tokens": 4096,
                "temperature": 0.7,
                "is_active": pid == data.get("active_provider"),
            }
            providers_dict[pid] = entry
        else:
            entry = providers_dict[pid]
            if not entry.get("base_url"):
                entry["base_url"] = p_info.get("base_url")

    data["providers"] = providers_dict
    mcp_raw = os.environ.get("ZENITH_MCP_SERVERS", "").strip()
    if mcp_raw:
        try:
            parsed = json.loads(mcp_raw)
            mcp_servers: dict[str, dict] = {}
            for name, cfg in parsed.items():
                if isinstance(cfg, dict) and cfg.get("command"):
                    mcp_servers[str(name)] = {
                        "command": str(cfg["command"]),
                        "args": list(cfg.get("args") or []),
                        "env": dict(cfg.get("env") or {}),
                    }
                else:
                    logger.warning(
                        "MCP config: skipping invalid server '%s' (missing command)", name
                    )
            if mcp_servers:
                data["mcp_servers"] = mcp_servers
        except json.JSONDecodeError as e:
            logger.warning("Invalid ZENITH_MCP_SERVERS JSON — MCP servers disabled: %s", e)
    hooks_raw = os.environ.get("ZENITH_HOOKS", "").strip()
    if hooks_raw:
        hooks_cfg = parse_hooks_env(hooks_raw)
        if hooks_cfg:
            data["hooks"] = hooks_cfg
    compaction_raw = os.environ.get("ZENITH_CONTEXT_COMPACTION_THRESHOLD", "").strip()
    if compaction_raw:
        try:
            val = float(compaction_raw)
            if 0.0 <= val <= 1.0:
                data["context_compaction_threshold"] = val
            else:
                logger.warning(
                    "ZENITH_CONTEXT_COMPACTION_THRESHOLD must be in [0,1], got %r — ignored",
                    compaction_raw,
                )
        except ValueError:
            logger.warning(
                "Invalid ZENITH_CONTEXT_COMPACTION_THRESHOLD %r — ignored", compaction_raw
            )
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
