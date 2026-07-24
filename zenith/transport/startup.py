"""Startup validation — REST endpoints for frontend initialization checks."""

from __future__ import annotations

import json
import logging
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from zenith.config.loader import load_config, save_config
from zenith.config.settings import AppSettings
from zenith.config.env import require_int, require_float
from zenith.providers.registry import ProviderRegistry
from zenith.providers.llm_provider import LLMProvider
from zenith.db.repository import load_catalog
from zenith.db.connection import resolve_db_path

_DEFAULT_MAX_TOKENS = require_int("ZENITH_MAX_TOKENS")
_DEFAULT_TEMPERATURE = require_float("ZENITH_TEMPERATURE")

logger = logging.getLogger(__name__)


class StartupStatus(str, Enum):
    READY = "ready"
    CONFIGURATION_REQUIRED = "configuration_required"


class MissingItem(str, Enum):
    PROVIDER = "provider"
    MODEL = "model"
    API_KEY = "apiKey"
    CONFIG_FILE = "configFile"
    WORKSPACE = "workspace"
    DB_PATH = "dbPath"


class StartupResult(BaseModel):
    status: StartupStatus
    missing: list[MissingItem] = Field(default_factory=list)
    active_provider: str = ""
    active_model: str = ""
    provider_count: int = 0
    message: str = ""


class ProviderSetupRequest(BaseModel):
    provider: str
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    max_tokens: int = _DEFAULT_MAX_TOKENS
    temperature: float = _DEFAULT_TEMPERATURE


class ProviderSetupResult(BaseModel):
    valid: bool
    provider: str = ""
    model: str = ""
    message: str = ""


def validate_startup(workspace_root: str = ".") -> StartupResult:
    """Validate all startup prerequisites and return structured result."""
    missing: list[MissingItem] = []

    try:
        config = load_config(workspace_root)
    except Exception as e:
        logger.error("Config load failed: %s", e)
        return StartupResult(
            status=StartupStatus.CONFIGURATION_REQUIRED,
            missing=[MissingItem.CONFIG_FILE],
            message=f"Could not load configuration: {e}",
        )

    providers = config.providers or {}
    active = config.active_provider
    catalog = load_catalog()
    known_providers = set(catalog.get("providers", {}).keys())

    if not providers:
        missing.append(MissingItem.PROVIDER)
    elif not active or (active not in providers and active not in known_providers):
        missing.append(MissingItem.PROVIDER)

    provider_config = providers.get(active) if active else None
    active_model = ""
    if provider_config:
        active_model = provider_config.model or ""

    if not active_model:
        missing.append(MissingItem.MODEL)

    if provider_config:
        has_key = bool(provider_config.api_key and provider_config.api_key.strip())
        if not has_key:
            missing.append(MissingItem.API_KEY)

    if not config.workspace_root or not Path(config.workspace_root).exists():
        missing.append(MissingItem.WORKSPACE)

    status = StartupStatus.READY if not missing else StartupStatus.CONFIGURATION_REQUIRED
    message = ""
    if missing:
        items = ", ".join(m.value for m in missing)
        message = f"Missing configuration: {items}"

    return StartupResult(
        status=status,
        missing=missing,
        active_provider=active or "",
        active_model=active_model,
        provider_count=len(providers),
        message=message,
    )


async def validate_provider_setup(request: ProviderSetupRequest, workspace_root: str = ".") -> ProviderSetupResult:
    """Validate provider configuration during setup flow with a real API call."""
    config = load_config(workspace_root)
    providers = config.providers or {}

    if request.provider not in providers and not request.api_key:
        return ProviderSetupResult(
            valid=False,
            provider=request.provider,
            message=f"Provider '{request.provider}' is not configured and no API key provided.",
        )

    provider_config = providers.get(request.provider)
    api_key = request.api_key or (provider_config.api_key if provider_config else "")
    model = request.model or (provider_config.model if provider_config else "")

    if not api_key.strip():
        logger.info("Validation failed for '%s': API key is required", request.provider)
        return ProviderSetupResult(
            valid=False,
            provider=request.provider,
            model=model,
            message="API key is required.",
        )

    if not model.strip():
        logger.info("Validation failed for '%s': model is required", request.provider)
        return ProviderSetupResult(
            valid=False,
            provider=request.provider,
            message="Model selection is required.",
        )

    logger.info("Validating provider '%s' with model '%s' via real API call...", request.provider, model)
    import asyncio
    try:
        import litellm
        litellm.drop_params = True

        temp_provider = LLMProvider(
            name=request.provider,
            api_key=api_key,
            base_url=request.base_url or getattr(provider_config, "base_url", None) or "",
            model=model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        validation_timeout = require_int("ZENITH_VALIDATION_TIMEOUT")
        await asyncio.wait_for(
            temp_provider.complete([{"role": "user", "content": "Say OK"}]),
            timeout=validation_timeout,
        )
        logger.info("Provider '%s' validation succeeded (API call returned OK)", request.provider)
    except ImportError:
        # litellm not installed — fall back to format check only
        logger.warning("litellm not available — provider validation skipped")
        catalog = load_catalog()
        catalog_entry = catalog["providers"].get(request.provider)
        if catalog_entry:
            expected = catalog_entry.get("api_key_prefix")
            if expected and not api_key.strip().startswith(expected):
                logger.info("Validation failed for '%s': API key format mismatch (expected %s...)", request.provider, expected)
                return ProviderSetupResult(
                    valid=False,
                    provider=request.provider,
                    model=model,
                    message=f"API key format looks wrong. {request.provider.title()} keys typically start with '{expected}'",
                )
    except asyncio.TimeoutError:
        timeout_sec = require_int("ZENITH_VALIDATION_TIMEOUT")
        logger.warning("Provider validation timed out for '%s' after %ds", request.provider, timeout_sec)
        return ProviderSetupResult(
            valid=False,
            provider=request.provider,
            model=model,
            message=f"Validation timed out after {timeout_sec}s. The provider may be unreachable.",
        )
    except Exception as e:
        logger.warning("Provider validation FAILED for '%s': %s", request.provider, e)
        return ProviderSetupResult(
            valid=False,
            provider=request.provider,
            model=model,
            message=str(e),
        )

    return ProviderSetupResult(
        valid=True,
        provider=request.provider,
        model=model,
        message="Configuration valid.",
    )


class ProviderConfigResponse(BaseModel):
    active_provider: str = ""
    providers: dict[str, dict[str, Any]] = {}


def get_provider_config(db_path: str | None = None) -> ProviderConfigResponse:
    """Return the current provider configuration directly from zenith.db,
    enriched with full model specs from the catalog."""
    import sqlite3

    db_path = db_path or resolve_db_path()
    if not Path(db_path).exists():
        return ProviderConfigResponse()

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT value FROM app_settings WHERE key = 'active_provider'")
        active_row = cursor.fetchone()
        active = active_row["value"] if active_row else "nvidia"

        cursor.execute("SELECT * FROM providers")
        p_rows = cursor.fetchall()
        result_providers: dict[str, dict[str, Any]] = {}
        for r in p_rows:
            pid = r["id"]
            p_dict = dict(r)
            cursor.execute(
                "SELECT id, name, context_window, description, is_default FROM provider_models WHERE provider_id = ?",
                (pid,),
            )
            m_rows = cursor.fetchall()

            catalog = load_catalog()
            catalog_models = {
                m["id"]: m
                for m in catalog.get("providers", {}).get(pid, {}).get("models", [])
            }

            enriched_models = []
            for m in m_rows:
                m_dict = dict(m)
                cat = catalog_models.get(m_dict["id"], {})
                m_dict["parameters"] = cat.get("parameters")
                m_dict["architecture"] = cat.get("architecture")
                m_dict["input_modalities"] = cat.get("input_modalities")
                m_dict["output_modalities"] = cat.get("output_modalities")
                m_dict["tags"] = cat.get("tags")
                m_dict["model_capabilities"] = cat.get("model_capabilities")
                m_dict["speed_tier"] = cat.get("speed_tier")
                m_dict["best_for"] = cat.get("best_for")
                enriched_models.append(m_dict)

            p_dict["models"] = enriched_models
            p_dict["swatch"] = json.loads(p_dict.get("swatch_json", "[]"))
            result_providers[pid] = p_dict
        conn.close()
        return ProviderConfigResponse(active_provider=active, providers=result_providers)
    except Exception as e:
        logger.warning("Failed to fetch provider config from DB: %s", e)
        return ProviderConfigResponse()


def save_provider_setup(request: ProviderSetupRequest, db_path: str | None = None) -> ProviderSetupResult:
    """Save provider configuration directly to zenith.db."""
    import sqlite3
    from datetime import datetime

    db_path = db_path or resolve_db_path()

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        cursor.execute("SELECT * FROM providers WHERE id = ?", (request.provider,))
        existing = cursor.fetchone()

        if existing:
            new_key = request.api_key if request.api_key.strip() else existing["api_key"]
            new_model = request.model if request.model.strip() else existing["model"]
            new_base = request.base_url if request.base_url.strip() else existing["base_url"]
            cursor.execute(
                """
                UPDATE providers
                SET api_key = ?, model = ?, base_url = ?, max_tokens = ?, temperature = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_key, new_model, new_base, request.max_tokens, request.temperature, now, request.provider),
            )
        else:
            cursor.execute(
                """
                INSERT INTO providers (id, name, description, api_key, model, base_url, max_tokens, temperature, is_active, swatch_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '[]', ?)
                """,
                (
                    request.provider,
                    request.provider.title(),
                    "",
                    request.api_key,
                    request.model,
                    request.base_url,
                    request.max_tokens,
                    request.temperature,
                    now,
                ),
            )

        cursor.execute("UPDATE providers SET is_active = 0")
        cursor.execute("UPDATE providers SET is_active = 1 WHERE id = ?", (request.provider,))
        cursor.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('active_provider', ?)",
            (request.provider,),
        )
        conn.commit()
        conn.close()

        logger.info("Saved provider config for '%s' to DB %s", request.provider, db_path)
        return ProviderSetupResult(
            valid=True,
            provider=request.provider,
            model=request.model or "",
            message="Configuration saved to database.",
        )
    except Exception as e:
        logger.error("Failed to save provider setup to DB: %s", e)
        return ProviderSetupResult(
            valid=False,
            provider=request.provider,
            model=request.model,
            message=f"Failed to save to database: {e}",
        )
