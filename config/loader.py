import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from db.connection import resolve_db_path
from db.provider_config_repo import read_active_provider, read_providers

from .settings import AppSettings

logger = logging.getLogger(__name__)

_catalog_cache: dict | None = None
_validated_once: bool = False


def _load_catalog() -> dict:
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache
    from db.repository import load_catalog
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
    # Load API keys from .keys file in the workspace root if present
    keys_path = Path('.keys')
    if keys_path.is_file():
        for line in keys_path.read_text().splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
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

    # Environment key mapping for provider fallbacks from .keys / process environment
    env_key_map = {
        "nvidia": ["NVIDIA_AI_API_KEY", "nvidia_ai_api_key", "NVIDIA_API_KEY"],
        "groq": ["GROQ_API_KEY", "groq_api_key"],
        "openrouter": ["OPENROUTER_API", "openrouter_api", "OPENROUTER_API_KEY"],
        "google": ["GOOGLE_AI_STUDIO", "google_ai_studio", "GOOGLE_API_KEY", "GEMINI_API_KEY"],
        "openai": ["OPENAI_API_KEY", "openai_api_key"],
        "anthropic": ["ANTHROPIC_API_KEY", "anthropic_api_key"],
    }

    catalog = _load_catalog()
    catalog_providers = catalog.get("providers", {})

    for pid, p_info in catalog_providers.items():
        if pid not in providers_dict:
            providers_dict[pid] = {
                "api_key": "",
                "model": p_info.get("default_model"),
                "base_url": p_info.get("base_url"),
                "max_tokens": 4096,
                "temperature": 0.7,
                "is_active": pid == data.get("active_provider", catalog.get("default_active_provider")),
            }

        # Inject API key from environment if current api_key is empty
        if not providers_dict[pid].get("api_key"):
            for env_var in env_key_map.get(pid, []):
                val = os.environ.get(env_var)
                if val and val.strip():
                    providers_dict[pid]["api_key"] = val.strip()
                    break

    data["providers"] = providers_dict

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
