from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from server.api import validation_state
from server.api.schemas import (
    ProviderModelInfo,
    ValidationError,
    ValidationResult,
    ValidationStep,
    ValidationStepStatus,
)
from server.config.constants import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_LLM_MAX_TOKENS,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_VALIDATION_TIMEOUT,
    URL_SCHEME_RE,
    VALIDATION_TIMEOUT_ENV,
    default_max_tokens_for_context,
)
from server.config.env import optional_int
from server.providers.llm_provider import LLMProvider, _extract_clean_message
from server.storage import StorageHome, load_catalog, resolve_home
from server.storage.provider_config import (
    read_providers as read_stored_providers,
)
from server.storage.provider_config import (
    save_provider_config,
    upsert_provider_models,
)

logger = logging.getLogger(__name__)
STEP_LABELS: dict[str, str] = {
    "config": "Configuration",
    "base_url": "Base URL",
    "api_key": "API Key",
    "connection": "Connection",
    "auth": "Authentication",
    "models": "Model Catalog",
    "smoke_test": "Smoke Test",
    "save": "Save",
}
_AUTH_REJECTION_HINTS = (
    "authentication",
    "unauthorized",
    "invalid api key",
    "api key invalid",
    "api_key_invalid",
    "401",
    "403",
)


def _is_auth_rejection(exc: Exception) -> bool:
    if exc.__class__.__name__.endswith("AuthenticationError"):
        return True
    msg = (_extract_clean_message(exc) or "").lower()
    return any(hint in msg for hint in _AUTH_REJECTION_HINTS)


def _step_event(key: str, status: ValidationStepStatus, message: str = "") -> dict:
    return {
        "type": "step",
        "key": key,
        "label": STEP_LABELS.get(key, key),
        "status": status.value,
        "message": message,
    }


def _result_event(
    valid: bool,
    provider: str,
    steps: list[ValidationStep],
    models: list[ProviderModelInfo],
    error: ValidationError | None,
) -> dict:
    payload = ValidationResult(
        valid=valid, provider=provider, steps=steps, models=models, error=error
    )
    return {"type": "result", **payload.model_dump()}


def _map_models(raw: Any) -> list[ProviderModelInfo]:
    if not isinstance(raw, dict):
        return []
    data = raw.get("data", [])
    if not isinstance(data, list):
        return []
    out: list[ProviderModelInfo] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        mid = str(item.get("id") or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        out.append(
            ProviderModelInfo(
                id=mid,
                name=str(item.get("name") or mid),
                context_window=int(
                    item.get("context_window")
                    or item.get("context_length")
                    or DEFAULT_CONTEXT_WINDOW
                ),
                description=str(item.get("description") or ""),
                is_default=bool(item.get("is_default", False)),
                status=str(item.get("status") or "active"),
                tags=[str(t) for t in item.get("tags", [])]
                if isinstance(item.get("tags"), list)
                else [],
            )
        )
    return out


def _resolve_config(
    provider_id: str, api_key: str, base_url: str, model: str, home: StorageHome
) -> tuple[dict, dict]:
    catalog = load_catalog(home)
    entry = catalog.get("providers", {}).get(provider_id) or {}
    stored = read_stored_providers(home).get(provider_id) or {}
    resolved_key = (api_key or "").strip() or (stored.get("api_key") or "")
    catalog_base = (entry.get("base_url") or "").strip()
    if entry.get("base_url_style") != "user" and catalog_base:
        resolved_base = (base_url or "").strip() or catalog_base
    else:
        resolved_base = (base_url or "").strip() or (stored.get("base_url") or "") or catalog_base
    resolved_model = (
        (model or "").strip() or (stored.get("model") or "") or (entry.get("default_model") or "")
    )
    max_tokens = stored.get("max_tokens")
    temperature = stored.get("temperature")
    if max_tokens is None or temperature is None:
        models = entry.get("models", [])
        for m in models:
            if m.get("id") == resolved_model:
                ctx = m.get("context_window", DEFAULT_CONTEXT_WINDOW)
                if max_tokens is None:
                    max_tokens = m.get("max_output_tokens", default_max_tokens_for_context(ctx))
                if temperature is None:
                    temperature = m.get("default_temperature", DEFAULT_LLM_TEMPERATURE)
                break
    if max_tokens is None:
        max_tokens = DEFAULT_LLM_MAX_TOKENS
    if temperature is None:
        temperature = DEFAULT_LLM_TEMPERATURE
    config = {
        "api_key": resolved_key,
        "base_url": resolved_base,
        "model": resolved_model,
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
        "adapter": entry.get("adapter", "openai_compat"),
        "litellm_prefix": entry.get("litellm_prefix", ""),
        "requires_api_key": bool(entry.get("requires_api_key", True)),
        "api_key_prefix": entry.get("api_key_prefix"),
    }
    return (entry, config)


def _base_url_endpoint(base_url: str) -> str:
    return base_url.rstrip("/") + "/models"


async def validate_provider(
    provider_id: str,
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    home: StorageHome | None = None,
    workspace_root: str = ".",
) -> AsyncIterator[dict]:
    home = home or StorageHome(resolve_home())
    steps: dict[str, ValidationStep] = {
        key: ValidationStep(key=key, label=label) for key, label in STEP_LABELS.items()
    }

    def _mask_key(value: str) -> str:
        if not value:
            return ""
        if len(value) <= 4:
            return "*" * len(value)
        return f"{value[:4]}...{value[-2:]}" if len(value) > 8 else value[:4] + "***"

    logger.info(
        "validate request: provider=%s api_key=%s base_url=%s model=%s",
        provider_id,
        _mask_key(api_key),
        base_url or "(default)",
        model or "(default)",
    )

    def _update(key: str, status: ValidationStepStatus, message: str = "") -> None:
        steps[key] = ValidationStep(key=key, label=STEP_LABELS[key], status=status, message=message)

    def _all_steps() -> list[ValidationStep]:
        return [steps[k] for k in STEP_LABELS]

    try:
        entry, cfg = _resolve_config(provider_id, api_key, base_url, model, home)
    except Exception as e:
        logger.warning("validate '%s': config resolution failed: %s", provider_id, e)
        _update("config", ValidationStepStatus.FAILED, str(e))
        yield _step_event("config", ValidationStepStatus.FAILED, str(e))
        yield _result_event(
            False, provider_id, _all_steps(), [], ValidationError(code="CONFIG", message=str(e))
        )
        return
    if not entry:
        msg = f"Unknown provider '{provider_id}'."
        _update("config", ValidationStepStatus.FAILED, msg)
        yield _step_event("config", ValidationStepStatus.FAILED, msg)
        yield _result_event(
            False,
            provider_id,
            _all_steps(),
            [],
            ValidationError(code="UNKNOWN_PROVIDER", message=msg),
        )
        return
    logger.info(
        "validate resolved: provider=%s name=%s adapter=%s base_url=%s model=%s key_present=%s key_prefix=%s",
        provider_id,
        entry.get("name", provider_id),
        entry.get("adapter"),
        cfg["base_url"],
        cfg["model"],
        bool(cfg["api_key"]),
        cfg.get("api_key_prefix"),
    )
    _update("config", ValidationStepStatus.SUCCESS, f"Using {entry.get('name', provider_id)}")
    yield _step_event(
        "config", ValidationStepStatus.SUCCESS, f"Using {entry.get('name', provider_id)}"
    )
    _update("base_url", ValidationStepStatus.RUNNING)
    yield _step_event("base_url", ValidationStepStatus.RUNNING)
    base_url = cfg["base_url"]
    if not base_url:
        msg = "Base URL is required."
        _update("base_url", ValidationStepStatus.FAILED, msg)
        yield _step_event("base_url", ValidationStepStatus.FAILED, msg)
        yield _result_event(
            False,
            provider_id,
            _all_steps(),
            [],
            ValidationError(code="MISSING_BASE_URL", message=msg),
        )
        return
    if not URL_SCHEME_RE.match(base_url):
        msg = f"Base URL '{base_url}' must start with http:// or https://"
        _update("base_url", ValidationStepStatus.FAILED, msg)
        yield _step_event("base_url", ValidationStepStatus.FAILED, msg)
        yield _result_event(
            False,
            provider_id,
            _all_steps(),
            [],
            ValidationError(code="INVALID_BASE_URL", message=msg),
        )
        return
    _update("base_url", ValidationStepStatus.SUCCESS, base_url)
    yield _step_event("base_url", ValidationStepStatus.SUCCESS, base_url)
    _update("api_key", ValidationStepStatus.RUNNING)
    yield _step_event("api_key", ValidationStepStatus.RUNNING)
    api_key = cfg["api_key"]
    if cfg["requires_api_key"] and (not api_key.strip()):
        msg = "API key is required."
        _update("api_key", ValidationStepStatus.FAILED, msg)
        yield _step_event("api_key", ValidationStepStatus.FAILED, msg)
        yield _result_event(
            False,
            provider_id,
            _all_steps(),
            [],
            ValidationError(code="MISSING_API_KEY", message=msg),
        )
        return
    prefix = cfg.get("api_key_prefix")
    key_note = "Optional (no key required)" if not cfg["requires_api_key"] else "Provided"
    if prefix and api_key.strip() and (not api_key.strip().startswith(prefix)):
        key_note = f"Key does not start with '{prefix}…' — the auth step will verify it"
    _update("api_key", ValidationStepStatus.SUCCESS, key_note)
    yield _step_event("api_key", ValidationStepStatus.SUCCESS, key_note)
    models: list[ProviderModelInfo] = []
    timeout = optional_int(VALIDATION_TIMEOUT_ENV, DEFAULT_VALIDATION_TIMEOUT)
    endpoint = _base_url_endpoint(base_url)
    headers = {"Authorization": f"Bearer {api_key}"} if api_key.strip() else {}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(endpoint, headers=headers)
    except httpx.TimeoutException:
        msg = f"Connection timed out after {timeout}s."
        _update("connection", ValidationStepStatus.FAILED, msg)
        yield _step_event("connection", ValidationStepStatus.FAILED, msg)
        yield _result_event(
            False,
            provider_id,
            _all_steps(),
            [],
            ValidationError(code="CONNECTION_TIMEOUT", message=msg),
        )
        return
    except httpx.HTTPError as exc:
        msg = f"Could not reach {endpoint}: {_extract_clean_message(exc)}"
        _update("connection", ValidationStepStatus.FAILED, msg)
        yield _step_event("connection", ValidationStepStatus.FAILED, msg)
        yield _result_event(
            False,
            provider_id,
            _all_steps(),
            [],
            ValidationError(code="CONNECTION_FAILED", message=msg),
        )
        return
    _update("connection", ValidationStepStatus.SUCCESS, endpoint)
    yield _step_event("connection", ValidationStepStatus.SUCCESS, endpoint)
    if resp.status_code in (401, 403):
        msg = "Authentication failed — the API key was rejected."
        _update("auth", ValidationStepStatus.FAILED, msg)
        yield _step_event("auth", ValidationStepStatus.FAILED, msg)
        yield _result_event(
            False, provider_id, _all_steps(), [], ValidationError(code="AUTH_FAILED", message=msg)
        )
        return
    auth_msg = f"Authenticated (HTTP {resp.status_code})"
    auth_ok = True
    probe_model = cfg["model"]
    if cfg["requires_api_key"] and api_key.strip() and probe_model:
        try:
            import litellm

            litellm.drop_params = True
            probe_provider = LLMProvider(
                name=provider_id,
                api_key=api_key,
                base_url=base_url,
                model=probe_model,
                max_tokens=1,
                temperature=0.0,
                enable_thinking=False,
            )
            await asyncio.wait_for(
                probe_provider.complete([{"role": "user", "content": "Say OK"}]), timeout=timeout
            )
        except ImportError:
            logger.warning("litellm not available - auth probe skipped")
        except TimeoutError:
            auth_msg = "Authenticated (key accepted, probe timed out)"
        except Exception as exc:
            if _is_auth_rejection(exc):
                auth_msg = f"Authentication failed - {_extract_clean_message(exc)}"
                auth_ok = False
            else:
                auth_msg = "Authenticated (key accepted)"
    if not auth_ok:
        _update("auth", ValidationStepStatus.FAILED, auth_msg)
        yield _step_event("auth", ValidationStepStatus.FAILED, auth_msg)
        yield _result_event(
            False,
            provider_id,
            _all_steps(),
            [],
            ValidationError(code="AUTH_FAILED", message=auth_msg),
        )
        return
    _update("auth", ValidationStepStatus.SUCCESS, auth_msg)
    yield _step_event("auth", ValidationStepStatus.SUCCESS, auth_msg)
    _update("models", ValidationStepStatus.RUNNING)
    yield _step_event("models", ValidationStepStatus.RUNNING)
    if resp.status_code == 200:
        try:
            models = _map_models(resp.json())
        except Exception as e:
            logger.debug("validate '%s': model catalog parse failed: %s", provider_id, e)
            models = []
        for m in models:
            yield {"type": "model", "model": m.model_dump()}
    msg = (
        f"Discovered {len(models)} model(s)" if models else "No models returned — use manual entry"
    )
    _update("models", ValidationStepStatus.SUCCESS, msg)
    yield _step_event("models", ValidationStepStatus.SUCCESS, msg)
    _update("smoke_test", ValidationStepStatus.RUNNING)
    yield _step_event("smoke_test", ValidationStepStatus.RUNNING)
    smoke_model = cfg["model"]
    smoke_error = ""
    if smoke_model:
        try:
            import litellm

            litellm.drop_params = True
            temp_provider = LLMProvider(
                name=provider_id,
                api_key=api_key,
                base_url=base_url,
                model=smoke_model,
                max_tokens=cfg["max_tokens"],
                temperature=cfg["temperature"],
            )
            await asyncio.wait_for(
                temp_provider.complete([{"role": "user", "content": "Say OK"}]), timeout=timeout
            )
        except ImportError:
            logger.warning("litellm not available — smoke test skipped")
        except TimeoutError:
            smoke_error = f"Smoke test timed out after {timeout}s"
        except Exception as exc:
            smoke_error = _extract_clean_message(exc) or str(exc)
    else:
        smoke_error = "No model selected for smoke test"
    if smoke_error:
        _update("smoke_test", ValidationStepStatus.FAILED, smoke_error)
        yield _step_event("smoke_test", ValidationStepStatus.FAILED, smoke_error)
        yield _result_event(
            False,
            provider_id,
            _all_steps(),
            models,
            ValidationError(code="SMOKE_TEST_FAILED", message=smoke_error),
        )
        return
    _update("smoke_test", ValidationStepStatus.SUCCESS, "Completed 'Say OK' round-trip")
    yield _step_event("smoke_test", ValidationStepStatus.SUCCESS, "Completed 'Say OK' round-trip")
    _update("save", ValidationStepStatus.RUNNING)
    yield _step_event("save", ValidationStepStatus.RUNNING)
    try:
        save_provider_config(
            home,
            provider=provider_id,
            api_key=api_key,
            model=smoke_model,
            base_url=base_url or None,
            max_tokens=cfg["max_tokens"],
            temperature=cfg["temperature"],
            set_active=False,
        )
        if entry.get("custom_flow") and models:
            upsert_provider_models(home, provider_id, models=[m.model_dump() for m in models])
    except Exception as e:
        logger.warning("validate '%s': save failed: %s", provider_id, e)
        msg = f"Failed to save configuration: {e}"
        _update("save", ValidationStepStatus.FAILED, msg)
        yield _step_event("save", ValidationStepStatus.FAILED, msg)
        yield _result_event(
            False,
            provider_id,
            _all_steps(),
            models,
            ValidationError(code="SAVE_FAILED", message=msg),
        )
        return
    validation_state.mark_validated(provider_id)
    _update("save", ValidationStepStatus.SUCCESS, "Configuration saved")
    yield _step_event("save", ValidationStepStatus.SUCCESS, "Configuration saved")
    yield _result_event(True, provider_id, _all_steps(), models, None)


async def validate_provider_collect(
    provider_id: str,
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    home: StorageHome | None = None,
    workspace_root: str = ".",
) -> ValidationResult:
    result: ValidationResult | None = None
    async for event in validate_provider(
        provider_id, api_key, base_url, model, home, workspace_root
    ):
        if event.get("type") == "result":
            result = ValidationResult(**{k: v for k, v in event.items() if k != "type"})
    if result is None:
        result = ValidationResult(
            valid=False,
            provider=provider_id,
            error=ValidationError(code="UNKNOWN", message="No result"),
        )
    return result
