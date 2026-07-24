import json
import os
import sys
import sqlite3
import logging
from pathlib import Path
from dotenv import load_dotenv
from .settings import AppSettings
from .providers import ProviderConfig
from zenith.db.connection import resolve_db_path

logger = logging.getLogger(__name__)

_catalog_cache: dict | None = None
_validated_once: bool = False


def _load_catalog() -> dict:
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache
    from zenith.db.repository import load_catalog
    _catalog_cache = load_catalog()
    return _catalog_cache


def providers_requiring_key() -> set[str]:
    catalog = _load_catalog()
    return {
        pid for pid, p in catalog["providers"].items()
        if p.get("requires_api_key", True)
    }


def load_config(workspace_root: str = ".") -> AppSettings:
    load_dotenv()

    data: dict = {}
    db_path = resolve_db_path()
    data["db_path"] = db_path

    if Path(db_path).exists():
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_settings'")
            if cursor.fetchone():
                cursor.execute("SELECT value FROM app_settings WHERE key = 'active_provider'")
                active_row = cursor.fetchone()
                if active_row and active_row["value"]:
                    data["active_provider"] = active_row["value"]

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='providers'")
            if cursor.fetchone():
                cursor.execute("SELECT * FROM providers")
                p_rows = cursor.fetchall()
                if p_rows:
                    providers_dict = {}
                    for r in p_rows:
                        providers_dict[r["id"]] = {
                            "api_key": r["api_key"],
                            "model": r["model"],
                            "base_url": r["base_url"],
                            "max_tokens": r["max_tokens"],
                            "temperature": r["temperature"],
                            "is_active": bool(r["is_active"]),
                        }
                    data["providers"] = providers_dict
            conn.close()
        except Exception as e:
            logger.warning("Could not read config from DB '%s': %s", db_path, e)

    settings = AppSettings(**data)
    _validate_config(settings)
    return settings


def _validate_config(settings: AppSettings) -> None:
    """Run startup validation checks and log warnings for misconfigurations.
    
    Only runs once to avoid spamming logs on every load_config() call.
    """
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

    if not has_any_key and not any(
        getattr(cfg, "api_key", None) for cfg in providers.values()
    ):
        warnings.append(
            "No provider API keys found in zenith.db database. Configure at least one provider via setup wizard."
        )

    catalog = _load_catalog()
    if settings.active_provider not in providers and settings.active_provider not in catalog.get("providers", {}):
        warnings.append(
            f"Active provider '{settings.active_provider}' is not in the configured "
            f"providers list {list(providers.keys()) or '[]'}. "
            f"Set active provider in zenith.db."
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

    if warnings and os.getenv("ZENITH_STRICT_VALIDATION", "").strip().lower() in ("1", "true", "yes"):
        print("Configuration errors detected:", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)
        sys.exit(1)


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
