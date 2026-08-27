from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from server.api import validation_state
from server.config.constants import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_LLM_MAX_TOKENS,
    DEFAULT_LLM_TEMPERATURE,
)
from server.providers.validation import validate_provider
from server.storage import StorageHome, resolve_home
from server.storage.catalog_compat import load_catalog
from server.storage.provider_config import (
    read_provider_config_full,
    read_providers,
    save_provider_config,
    upsert_provider_models,
)

from .schemas import (
    ProviderCatalogItem,
    ProviderInfo,
    ProviderListResponse,
    ProviderModelInfo,
    ProviderModelListResponse,
    ProviderModelRequest,
    ProviderValidationRequest,
)

logger = logging.getLogger(__name__)
_CATALOG_META_KEYS = {
    "id",
    "name",
    "description",
    "adapter",
    "litellm_prefix",
    "default_model",
    "base_url",
    "api_key_prefix",
    "requires_api_key",
    "swatch",
    "capabilities",
    "config_fields",
    "env_keys",
    "is_popular",
    "base_url_style",
    "supports_prompt_caching",
    "supports_thinking_headers",
    "custom_flow",
}


def build_provider_info(
    pid: str, p: dict[str, Any], catalog: dict, active_provider: str
) -> ProviderInfo:
    cat = catalog.get("providers", {}).get(pid) or {}
    has_key = bool(p.get("has_api_key"))
    status = validation_state.get_status(pid, has_key)
    options: dict[str, Any] = {}
    for k, v in cat.items():
        if k not in _CATALOG_META_KEYS and (not isinstance(v, (dict, list))):
            options[k] = v
    models: dict[str, ProviderModelInfo] = {}
    cat_models = cat.get("models", [])
    curated = bool(cat_models) and (not bool(cat.get("custom_flow", False)))
    if not curated:
        for m in p.get("models", []):
            try:
                models[m["id"]] = ProviderModelInfo(
                    id=m["id"],
                    name=m.get("name") or m["id"],
                    context_window=m.get("context_window") or DEFAULT_CONTEXT_WINDOW,
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
    for m in cat_models:
        mid = m.get("id")
        if not mid or mid in models:
            continue
        models[mid] = ProviderModelInfo(
            id=mid,
            name=m.get("name") or mid,
            context_window=m.get("context_window") or DEFAULT_CONTEXT_WINDOW,
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
        is_popular=bool(cat.get("is_popular", False)),
        base_url_style=cat.get("base_url_style") or "",
        supports_prompt_caching=bool(cat.get("supports_prompt_caching", False)),
        supports_thinking_headers=bool(cat.get("supports_thinking_headers", False)),
        custom_flow=bool(cat.get("custom_flow", False)),
        env_keys=cat.get("env_keys") or [],
    )


def _default_home() -> StorageHome:
    return StorageHome(resolve_home())


def get_provider_list(home: StorageHome | None = None) -> ProviderListResponse:
    home = home or _default_home()
    catalog = load_catalog(home)
    max_context_tokens = 0
    try:
        from server.config.loader import load_config

        max_context_tokens = int(load_config().max_context_tokens)
    except Exception:
        pass
    active: str = ""
    providers_dict: dict[str, dict[str, Any]] = {}
    try:
        active, providers_dict = read_provider_config_full(home)
    except Exception as e:
        logger.warning("get_provider_list: read failed: %s", e)
    ids = list(catalog.get("providers", {}).keys())
    for pid in providers_dict:
        if pid not in ids:
            ids.append(pid)
    infos: list[ProviderInfo] = []
    connected: list[str] = []
    for pid in ids:
        p = providers_dict.get(pid, {})
        info = build_provider_info(pid, p, catalog, active or "")
        infos.append(info)
        if info.has_api_key:
            connected.append(pid)
    return ProviderListResponse(
        all=infos, active=active or "", connected=connected, max_context_tokens=max_context_tokens
    )


def get_provider_catalog(home: StorageHome | None = None) -> list[ProviderCatalogItem]:
    home = home or _default_home()
    catalog = load_catalog(home)
    providers = catalog.get("providers", {})
    items: list[ProviderCatalogItem] = []
    for pid in providers:
        entry = providers[pid]
        items.append(
            ProviderCatalogItem(
                id=pid,
                name=entry.get("name") or pid,
                type="custom" if entry.get("custom_flow") else "default",
            )
        )
    seen: set[str] = set()
    ordered: list[ProviderCatalogItem] = []
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        ordered.append(item)
    return ordered


def get_provider_models(
    provider_id: str,
    offset: int = 0,
    limit: int = 50,
    home: StorageHome | None = None,
) -> ProviderModelListResponse:
    home = home or _default_home()
    catalog = load_catalog(home)
    active = ""
    providers_dict: dict[str, Any] = {}
    try:
        active, providers_dict = read_provider_config_full(home)
    except Exception as e:
        logger.warning("get_provider_models: read failed: %s", e)
    p = providers_dict.get(provider_id, {})
    info = build_provider_info(provider_id, p, catalog, active)
    all_models = list(info.models.values())
    total = len(all_models)
    safe_offset = max(0, offset)
    safe_limit = max(0, limit)
    page = all_models[safe_offset : safe_offset + safe_limit] if safe_limit else []
    return ProviderModelListResponse(models=page, total=total, offset=safe_offset, limit=safe_limit)


def set_provider_model(
    provider_id: str, request: ProviderModelRequest, home: StorageHome | None = None
) -> ProviderInfo:
    home = home or _default_home()
    model = request.model.strip()
    if not model:
        raise ValueError("Model is required.")
    existing = read_providers(home).get(provider_id, {})
    save_provider_config(
        home,
        provider=provider_id,
        api_key=existing.get("api_key", ""),
        model=model,
        base_url=existing.get("base_url", ""),
        max_tokens=existing.get("max_tokens", DEFAULT_LLM_MAX_TOKENS),
        temperature=existing.get("temperature", DEFAULT_LLM_TEMPERATURE),
        set_active=True,
    )
    upsert_provider_models(
        home,
        provider_id,
        models=[
            {
                "id": model,
                "name": model,
                "context_window": DEFAULT_CONTEXT_WINDOW,
                "description": "",
                "is_default": False,
            }
        ],
    )
    catalog = load_catalog(home)
    active, providers_dict = read_provider_config_full(home)
    p = providers_dict.get(provider_id, {})
    return build_provider_info(provider_id, p, catalog, active)


async def ndjson_validate_stream(
    provider_id: str,
    request: ProviderValidationRequest | None,
    home: StorageHome | None = None,
    on_success=None,
) -> AsyncIterator[str]:
    home = home or _default_home()
    req = request or ProviderValidationRequest()
    valid = False
    async for event in validate_provider(
        provider_id=provider_id,
        api_key=req.api_key,
        base_url=req.base_url,
        model=req.model,
        home=home,
    ):
        yield (json.dumps(event) + "\n")
        if event.get("type") == "result":
            valid = bool(event.get("valid"))
    if valid and on_success is not None:
        on_success(provider_id)
