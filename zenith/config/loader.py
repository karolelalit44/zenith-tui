import json
import os
import sys
import sqlite3
import logging
from pathlib import Path
from dotenv import load_dotenv
from .settings import AppSettings
from .providers import ProviderConfig

logger = logging.getLogger(__name__)

ENV_MAP = {
    "ZENITH_DB_PATH": (None, "db_path"),
}

API_KEY_FIELDS = {"api_key"}
PROVIDERS_REQUIRING_KEY = {"openai", "anthropic", "google", "groq", "openrouter", "nvidia"}


def load_config(workspace_root: str = ".") -> AppSettings:
    load_dotenv()

    data: dict = {}
    db_path = os.getenv("ZENITH_DB_PATH", "zenith.db")
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
    """Run startup validation checks and log warnings for misconfigurations."""
    warnings: list[str] = []

    providers = settings.providers or {}

    has_any_key = False
    for name, cfg in providers.items():
        if name in PROVIDERS_REQUIRING_KEY:
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

    if settings.active_provider not in providers and settings.active_provider != "custom":
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

    if warnings and os.getenv("ZENITH_STRICT_VALIDATION"):
        print("Configuration errors detected:", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)
        sys.exit(1)


CONFIG_FILENAME = "zenith.db"


def create_default_config(workspace_root: str = ".") -> Path:
    db_path = Path(workspace_root) / "zenith.db"
    if not db_path.exists():
        db_path.touch()
    return db_path


def save_config(settings: AppSettings, workspace_root: str = ".") -> Path:
    db_path = Path(workspace_root) / "zenith.db"
    return db_path
