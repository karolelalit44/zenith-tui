"""Provider validation — validate and persist provider configurations."""

from __future__ import annotations

import logging
from pathlib import Path

from config.env import require_int
from config.loader import load_config
from db.connection import resolve_db_path
from db.provider_config_repo import (
    read_provider_config_full,
    save_provider_config,
)
from db.repository import load_catalog
from providers.llm_provider import LLMProvider

from .schemas import ProviderConfigResponse, ProviderSetupRequest, ProviderSetupResult

logger = logging.getLogger(__name__)


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
    except TimeoutError:
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


def get_provider_config(db_path: str | None = None) -> ProviderConfigResponse:
    """Return the current provider configuration directly from db,
    enriched with full model specs from the catalog."""
    db_path = db_path or resolve_db_path()
    if not Path(db_path).exists():
        return ProviderConfigResponse()

    try:
        active, providers_dict = read_provider_config_full(db_path)
        return ProviderConfigResponse(active_provider=active, providers=providers_dict)
    except Exception as e:
        logger.warning("Failed to fetch provider config from DB: %s", e)
        return ProviderConfigResponse()


def save_provider_config_endpoint(request: ProviderSetupRequest, db_path: str | None = None) -> ProviderSetupResult:
    """Save provider configuration directly to zenith.db."""
    db_path = db_path or resolve_db_path()

    try:
        save_provider_config(
            provider=request.provider,
            api_key=request.api_key,
            model=request.model,
            base_url=request.base_url,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            db_path=db_path,
        )
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
