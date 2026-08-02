"""Provider validation — validate and persist provider configurations."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator

from server.api import validation_state
from server.config.env import require_int
from server.config.loader import load_config
from server.persistence.connection import resolve_db_path
from server.persistence.provider_config_repo import (
    read_provider_config_full,
    read_providers,
    save_provider_config,
    upsert_provider_models,
)
from server.persistence.repositories import load_catalog
from server.providers.llm_provider import LLMProvider
from server.providers.validation import validate_provider

from .schemas import (
    ProviderAuthRequest,
    ProviderConfigResponse,
    ProviderInfo,
    ProviderListResponse,
    ProviderModelInfo,
    ProviderModelRequest,
    ProviderSetupRequest,
    ProviderSetupResult,
    ProviderValidationRequest,
)

logger = logging.getLogger(__name__)

_CATALOG_META_KEYS = {
    "id", "name", "description", "adapter", "litellm_prefix", "default_model",
    "base_url", "api_key_prefix", "requires_api_key", "swatch", "capabilities",
    "config_fields",
}


def build_provider_info(
    pid: str,
    p: dict[str, Any],
    catalog: dict,
    active_provider: str,
) -> ProviderInfo:
    """Assemble a ProviderInfo from the DB row, catalog metadata, and session state."""
    cat = catalog.get("providers", {}).get(pid) or {}
    has_key = bool(p.get("has_api_key"))
    status = validation_state.get_status(pid, has_key)

    options: dict[str, Any] = {}
    for k, v in cat.items():
        if k not in _CATALOG_META_KEYS and not isinstance(v, (dict, list)):
            options[k] = v

    models: dict[str, ProviderModelInfo] = {}
    for m in p.get("models", []):
        try:
            models[m["id"]] = ProviderModelInfo(
                id=m["id"],
                name=m.get("name") or m["id"],
                context_window=m.get("context_window") or 128000,
                description=m.get("description") or "",
                is_default=bool(m.get("is_default")),
                parameters=m.get("parameters"),
                architecture=m.get("architecture"),
                input_modalities=m.get("input_modalities"),
                output_modalities=m.get("output_modalities"),
                tags=[str(t) for t in m.get("tags", [])] if m.get("tags") else [],
                model_capabilities=m.get("model_capabilities") or {},
                speed_tier=m.get("speed_tier"),
                best_for=m.get("best_for") or [],
                pricing=m.get("pricing") or {},
            )
        except Exception:
            continue

    for m in cat.get("models", []):
        mid = m.get("id")
        if not mid or mid in models:
            continue
        models[mid] = ProviderModelInfo(
            id=mid,
            name=m.get("name") or mid,
            context_window=m.get("context_window") or 128000,
            description=m.get("description") or "",
            is_default=bool(m.get("is_default")),
            parameters=m.get("parameters"),
            architecture=m.get("architecture"),
            input_modalities=m.get("input_modalities"),
            output_modalities=m.get("output_modalities"),
            tags=[str(t) for t in m.get("tags", [])] if m.get("tags") else [],
            model_capabilities=m.get("model_capabilities") or {},
            speed_tier=m.get("speed_tier"),
            best_for=m.get("best_for") or [],
            pricing=m.get("pricing") or {},
        )

    return ProviderInfo(
        id=pid,
        name=cat.get("name") or p.get("name") or pid,
        description=cat.get("description") or p.get("description") or "",
        adapter=cat.get("adapter") or p.get("adapter_type") or "openai_compat",
        swatch=cat.get("swatch") or p.get("swatch") or [],
        capabilities=cat.get("capabilities") or {},
        api_key_prefix=cat.get("api_key_prefix") or p.get("api_key_prefix"),
        requires_api_key=bool(cat.get("requires_api_key", True)),
        config_fields=cat.get("config_fields") or [],
        options=options,
        has_api_key=has_key,
        api_key_masked=p.get("api_key_masked") or "",
        validation_status=status,
        last_validation_error=validation_state.get_last_error(pid) if status == "failed" else "",
        is_active=pid == active_provider or bool(p.get("is_active")),
        model=p.get("model") or "",
        models=models,
    )


def get_provider_list(db_path: str | None = None) -> ProviderListResponse:
    """Build the full provider picker payload (catalog + DB state + session state)."""
    db_path = db_path or resolve_db_path()
    catalog = load_catalog()
    default = catalog.get("default_active_provider", "nvidia")

    if not Path(db_path).exists():
        infos = [
            build_provider_info(pid, {}, catalog, default)
            for pid in catalog.get("providers", {})
        ]
        return ProviderListResponse(all=infos, default={"active": default}, connected=[])

    try:
        active, providers_dict = read_provider_config_full(db_path)
    except Exception as e:
        logger.warning("get_provider_list: read failed: %s", e)
        active, providers_dict = default, {}

    ids = list(catalog.get("providers", {}).keys())
    for pid in providers_dict:
        if pid not in ids:
            ids.append(pid)

    infos: list[ProviderInfo] = []
    connected: list[str] = []
    for pid in ids:
        p = providers_dict.get(pid, {})
        info = build_provider_info(pid, p, catalog, active)
        infos.append(info)
        if info.has_api_key:
            connected.append(pid)
    return ProviderListResponse(all=infos, default={"active": active}, connected=connected)


def set_provider_auth(provider_id: str, request: ProviderAuthRequest, db_path: str | None = None) -> ProviderInfo:
    """Persist an API key without changing the active provider or model."""
    db_path = db_path or resolve_db_path()
    catalog = load_catalog()
    if provider_id not in catalog.get("providers", {}) and provider_id not in read_providers(db_path):
        raise ValueError(f"Unknown provider '{provider_id}'")
    save_provider_config(
        provider=provider_id,
        api_key=request.api_key,
        model="",
        base_url="",
        max_tokens=4096,
        temperature=0.7,
        db_path=db_path,
        set_active=False,
    )
    validation_state.reset(provider_id)
    active, providers_dict = read_provider_config_full(db_path)
    p = providers_dict.get(provider_id, {})
    return build_provider_info(provider_id, p, catalog, active)


def set_provider_model(provider_id: str, request: ProviderModelRequest, db_path: str | None = None) -> ProviderInfo:
    """Persist the selected model and make the provider active."""
    db_path = db_path or resolve_db_path()
    model = request.model.strip()
    if not model:
        raise ValueError("Model is required.")
    save_provider_config(
        provider=provider_id,
        api_key="",
        model=model,
        base_url="",
        max_tokens=4096,
        temperature=0.7,
        db_path=db_path,
        set_active=True,
    )
    upsert_provider_models(
        provider_id,
        models=[{"id": model, "name": model, "context_window": 128000, "description": "", "is_default": False}],
        db_path=db_path,
    )
    catalog = load_catalog()
    active, providers_dict = read_provider_config_full(db_path)
    p = providers_dict.get(provider_id, {})
    return build_provider_info(provider_id, p, catalog, active)


async def ndjson_validate_stream(
    provider_id: str,
    request: ProviderValidationRequest | None,
    db_path: str | None = None,
) -> AsyncIterator[str]:
    """Stream the 8-step validation pipeline as NDJSON lines."""
    db_path = db_path or resolve_db_path()
    req = request or ProviderValidationRequest()
    async for event in validate_provider(
        provider_id=provider_id,
        api_key=req.api_key,
        base_url=req.base_url,
        model=req.model,
        db_path=db_path,
    ):
        yield json.dumps(event) + "\n"


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
