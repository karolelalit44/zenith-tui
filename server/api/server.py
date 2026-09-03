from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from importlib.metadata import version as _get_version
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import StreamingResponse

from server.config.constants import HEALTH_PATH, WS_PATH
from server.config.loader import load_config
from server.providers.registry import ProviderRegistry
from server.storage import (
    StorageHome,
    ensure_materialized,
    public_profile,
    resolve_home,
    update_preferences,
)
from server.storage.usage_store import FileTokenUsageRepository
from server.toolkit import create_default_registry

if TYPE_CHECKING:
    from server.config.settings import AppSettings
from .middleware import wrap_handler
from .provider_validation import (
    get_provider_catalog,
    get_provider_list,
    get_provider_models,
    ndjson_validate_stream,
    set_provider_model,
)
from .schemas import (
    ProviderModelRequest,
    ProviderValidationRequest,
)
from .services.usage_service import UsageService
from .shutdown import GracefulShutdown
from .startup import validate_startup
from .websocket import ZenithHandler

try:
    __version__ = _get_version("zenith")
except Exception:
    __version__ = "0.1.0"
    
logger = logging.getLogger(__name__)
_WS_TOKEN = os.environ.get("ZENITH_WS_TOKEN", "")
_handler: ZenithHandler | None = None
_shutdown: GracefulShutdown | None = None
_home: StorageHome | None = None
_usage_service: UsageService | None = None


def _normalize_origin(origin: str) -> str | None:
    raw = origin.strip()
    if not raw:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme}://{host}{port}"


def _is_allowed_ws_origin(config: AppSettings, origin: str) -> bool:
    normalized = _normalize_origin(origin)
    if normalized is None:
        return config.allow_empty_ws_origin and not origin.strip()
    allowed = {
        value
        for candidate in config.allowed_ws_origins
        if (value := _normalize_origin(candidate)) is not None
    }
    return normalized in allowed


async def _do_startup() -> None:
    global _handler, _shutdown, _home, _usage_service
    logger.info("Starting Zenith backend...")
    _shutdown = GracefulShutdown()
    try:
        home = StorageHome(resolve_home())
        _home = home
        ensure_materialized(home)
        logger.info("Storage ready at %s", home.root)
        _usage_service = UsageService(FileTokenUsageRepository(home))
        config = load_config()
        logger.info(
            "Config loaded: provider=%s, home=%s",
            config.active_provider,
            config.home_dir,
        )
        from server.workspace.ignore import ensure_ignore_file, ignore_file_path

        ensure_ignore_file(config.workspace_root)
        logger.info("Ignore rules: %s", ignore_file_path(config.workspace_root))
        active_prov = config.providers.get(config.active_provider) if config.providers else None
        if active_prov:
            logger.info("Active provider: %s, model=%s", config.active_provider, active_prov.model)
        else:
            logger.warning(
                "Active provider '%s' not configured yet", config.active_provider or "(none)"
            )
        registry = ProviderRegistry.from_config(config.providers, config.active_provider)
        logger.info("Providers registered: %s", registry.list_providers())
        active_provider = registry.get(config.active_provider)
        tool_registry = create_default_registry(
            timeout=config.tools.max_bash_timeout, provider=active_provider
        )
        _handler = ZenithHandler(
            config=config, home=home, registry=registry, tool_registry=tool_registry
        )
        from server.toolkit.registry_validation import validate_registry

        validation_errors = validate_registry(tool_registry)
        if validation_errors:
            logger.error("Tool registry validation failed at startup:")
            for error in validation_errors:
                logger.error("  %s", error)
        # Intentional method wrap (pre-existing pattern); mypy dislikes it.
        _handler.handlers.dispatch = wrap_handler(_handler.handlers.dispatch)  # type: ignore[method-assign]
        logger.info("Handler initialized — server ready")
    except Exception as e:
        logger.error("Startup error encountered: %s", e)
        raise


async def _do_shutdown() -> None:
    global _handler, _shutdown, _test_handler, _usage_service
    logger.info("Shutting down Zenith backend...")
    _test_handler = None
    _usage_service = None
    try:
        if _shutdown:
            await _shutdown.shutdown()
    finally:
        _handler = None
        _shutdown = None
        logger.info("Zenith backend stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await _do_startup()
        yield
    finally:
        await _do_shutdown()


app = FastAPI(title="Zenith Backend", version=__version__, lifespan=lifespan)


@app.get(HEALTH_PATH)
async def health():
    storage_ok = _home is not None and _home.root.exists()
    return {
        "status": "ok",
        "handler": _handler is not None,
        "version": __version__,
        "storage": {
            "status": "ok" if storage_ok else "error",
            "home": str(_home.root) if _home else None,
        },
    }


@app.get("/status")
async def status():
    if _handler is None:
        return {"ready": False}
    return {
        "ready": True,
        "provider": _handler.config.active_provider,
        "workspace": _handler.config.workspace_root,
        "tools": _handler.tool_registry.list_tools(),
        "storage": {
            "status": "ok" if (_home and _home.root.exists()) else "error",
            "home": str(_home.root) if _home else None,
        },
    }


@app.get("/startup/validate")
def startup_validate():
    result = validate_startup()
    return result.model_dump()


@app.get("/startup/providers")
def startup_providers_list():
    data = get_provider_list()
    logger.info(
        "providers fetched: count=%d active=%s connected=%s",
        len(data.all),
        data.active or "(none)",
        ",".join(data.connected) or "(none)",
    )
    return data.model_dump()


@app.get("/providers")
def providers_list():
    """Provider list API — returns provider information only (no models)."""
    return [item.model_dump() for item in get_provider_catalog()]


@app.get("/providers/{provider_id}/models")
def providers_models(provider_id: str, offset: int = 0, limit: int = 50):
    """Models API — fetch models for a single provider from the backend."""
    return get_provider_models(provider_id, offset=offset, limit=limit).model_dump()


@app.post("/startup/providers/{provider_id}/validate")
async def startup_providers_validate(
    provider_id: str, request: ProviderValidationRequest | None = None, stream: int = 1
):
    if stream == 0:
        from server.providers.validation import validate_provider_collect

        result = await validate_provider_collect(
            provider_id=provider_id,
            api_key=request.api_key if request else "",
            base_url=request.base_url if request else "",
            model=request.model if request else "",
        )
        if result.valid:
            _reload_config_after_validate(provider_id)
        return result.model_dump()
    return StreamingResponse(
        ndjson_validate_stream(provider_id, request, on_success=_reload_config_after_validate),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache"},
    )


def _reload_config_after_validate(provider_id: str) -> None:
    if _handler is None:
        return
    try:
        _handler._reload_config()
        logger.info("Handler config reloaded after validating provider '%s'", provider_id)
    except Exception as e:
        logger.warning("Failed to reload config after validating '%s': %s", provider_id, e)


@app.post("/startup/providers/{provider_id}/model")
async def startup_providers_model(provider_id: str, request: ProviderModelRequest):
    logger.info("model selected: provider=%s model=%s", provider_id, request.model)
    try:
        info = set_provider_model(provider_id, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.warning("Failed to save model for '%s': %s", provider_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to save model: {e}")
    if _handler is not None:
        _handler._reload_config()
        logger.info(
            "Handler config reloaded after model change: provider=%s, model=%s",
            provider_id,
            request.model,
        )
    return info.model_dump()


@app.get("/profile")
def get_profile():
    """Masked user profile — never returns raw API keys (decision D5/D7)."""
    from server.storage import load_profile

    home = _home or StorageHome(resolve_home())
    return public_profile(load_profile(home))


@app.put("/profile/preferences")
def put_profile_preferences(request: dict):
    from fastapi import HTTPException

    if not isinstance(request, dict) or not request:
        raise HTTPException(status_code=400, detail="preferences object is required")
    try:
        home = _home or StorageHome(resolve_home())
        prefs = update_preferences(home, request)
        return {"ok": True, "preferences": prefs}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.warning("Failed to save preferences: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to save preferences: {e}")


@app.get("/usage/token-stats")
async def token_usage_stats(since: str | None = None, until: str | None = None):
    if _usage_service is None:
        return {"models": [], "totals": {}}
    return await _usage_service.get_token_stats(since=since, until=until)


@app.get("/usage/cost-summary")
async def token_cost_summary(period: str = "all"):
    if _usage_service is None:
        return {"data": []}
    return await _usage_service.get_cost_summary(period=period)


@app.get("/usage/steps/{session_id}")
async def token_usage_steps(session_id: str):
    if _usage_service is None:
        return {"steps": []}
    return await _usage_service.get_steps(session_id)


@app.get("/usage/efficiency/{session_id}")
async def token_usage_efficiency(session_id: str):
    if _usage_service is None:
        return {}
    return await _usage_service.get_efficiency(session_id)


@app.websocket(WS_PATH)
async def websocket_endpoint(websocket: WebSocket):
    if _handler is None:
        logger.warning("WebSocket rejected: handler not initialized")
        await websocket.close(code=1011, reason="Server not ready")
        return
    origin = websocket.headers.get("origin", "")
    if not _is_allowed_ws_origin(_handler.config, origin):
        logger.warning("WebSocket rejected: unexpected origin %s", origin)
        await websocket.close(code=4003, reason="Unexpected origin")
        return
    if _WS_TOKEN:
        query_token = websocket.query_params.get("token", "")
        if not secrets.compare_digest(query_token, _WS_TOKEN):
            logger.warning("WebSocket rejected: invalid token from %s", websocket.client)
            await websocket.close(code=4001, reason="Invalid auth token")
            return
    logger.info("WebSocket connecting from %s", websocket.client)
    await websocket.accept()
    try:
        await _handler.handle(websocket)
    except Exception:
        logger.exception("WebSocket handler error")
        raise


def create_app() -> FastAPI:
    return app
