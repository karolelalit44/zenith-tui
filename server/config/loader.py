import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from server.persistence.connection import resolve_db_path
from server.persistence.provider_config_repo import read_active_provider, read_providers

from .settings import AppSettings

logger = logging.getLogger(__name__)
_catalog_cache: dict | None = None
_validated_once: bool = False


def _load_catalog() -> dict:
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache
    from server.persistence.repositories import load_catalog

    _catalog_cache = load_catalog()
    return _catalog_cache


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
    keys_path = Path(".keys")
    if keys_path.is_file():
        for line in keys_path.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()
    data: dict = {}
    db_path = resolve_db_path()
    data["db_path"] = db_path
    providers_dict: dict[str, dict] = {}
    if Path(db_path).exists():
        try:
            active = read_active_provider(db_path)
            if active:
                data["active_provider"] = active
            providers_raw = read_providers(db_path)
            if providers_raw:
                providers_dict.update(providers_raw)
        except Exception as e:
            logger.warning("Could not read config from DB '%s': %s", db_path, e)
    catalog = _load_catalog()
    catalog_providers = catalog.get("providers", {})
    for pid, p_info in catalog_providers.items():
        if pid not in providers_dict:
            providers_dict[pid] = {
                "api_key": "",
                "model": "",
                "base_url": p_info.get("base_url"),
                "is_active": pid == data.get("active_provider"),
            }
        if not providers_dict[pid].get("api_key"):
            for env_var in p_info.get("env_keys") or []:
                val = os.environ.get(env_var)
                if val and val.strip():
                    providers_dict[pid]["api_key"] = val.strip()
                    break
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
            warnings.append(
                f"Provider '{name}' is configured in zenith.db but missing a valid API key."
            )
    if not has_any_key and (not any(getattr(cfg, "api_key", None) for cfg in providers.values())):
        warnings.append(
            "No provider API keys found in zenith.db database. Configure at least one provider via setup wizard."
        )
    catalog = _load_catalog()
    if settings.active_provider not in providers and settings.active_provider not in catalog.get(
        "providers", {}
    ):
        warnings.append(
            f"Active provider '{settings.active_provider}' is not in the configured providers list {list(providers.keys()) or '[]'}. Set active provider in zenith.db."
        )
    workspace = Path(settings.workspace_root)
    if not workspace.exists():
        warnings.append(f"Workspace root '{settings.workspace_root}' does not exist.")
    db_path = Path(settings.db_path)
    db_dir = db_path.parent if db_path.suffix else Path(".")
    if not db_dir.exists():
        try:
            db_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            warnings.append(f"Cannot create database directory '{db_dir}': {e}")
    for warning in warnings:
        logger.warning("Config: %s", warning)


def create_default_config(workspace_root: str = ".") -> Path:
    db_path = Path(resolve_db_path())
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        db_path.touch()
    return db_path


def save_config(settings: AppSettings, workspace_root: str = ".") -> Path:
    db_path = Path(resolve_db_path())
    return db_path
