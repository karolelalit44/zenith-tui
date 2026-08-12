from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from importlib.metadata import version as _get_version
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import StreamingResponse

from server.config.constants import HEALTH_PATH, TEST_WS_PATH, WS_PATH
from server.config.loader import load_config
from server.persistence.connection import Database, resolve_db_path
from server.persistence.logging import db_log
from server.persistence.repositories import TokenUsageRepository
from server.providers.registry import ProviderRegistry
from server.toolkit import create_default_registry

if TYPE_CHECKING:
    from server.mcp.manager import McpManager
from .middleware import wrap_handler
from .provider_validation import (
    get_model_selection,
    get_provider_catalog,
    get_provider_list,
    get_provider_models,
    ndjson_validate_stream,
    save_model_selection_endpoint,
    set_provider_model,
)
from .schemas import ModelStoreRequest, ProviderModelRequest, ProviderValidationRequest
from .shutdown import GracefulShutdown
from .startup import validate_startup
from .test_websocket import TestSimulationHandler
from .websocket import ZenithHandler

try:
    __version__ = _get_version("zenith")
except Exception:
    __version__ = "0.1.0"
logger = logging.getLogger(__name__)
_WS_TOKEN = os.environ.get("ZENITH_WS_TOKEN", "")
_handler: ZenithHandler | None = None
_shutdown: GracefulShutdown | None = None
_mcp_manager: McpManager | None = None
_database: Database | None = None
_test_handler: TestSimulationHandler | None = None


async def _do_startup() -> None:
    global _handler, _shutdown, _database, _test_handler
    logger.info("Starting Zenith backend...")
    _shutdown = GracefulShutdown()
    try:
        db = Database(resolve_db_path())
        _database = db
        await db.connect()
        logger.info("Database connected")
        db_log(
            "startup",
            status="ok",
            version=db.get_current_version() or "",
            mode=db.startup_result.get("mode", "") if db.startup_result else "",
            db=db.db_path,
        )
        from server.persistence.repositories import ProviderRepositoryDB

        provider_repo = ProviderRepositoryDB(db)
        await provider_repo.ensure_seeded()
        config = load_config()
        logger.info("Config loaded: provider=%s, db=%s", config.active_provider, config.db_path)
        active_prov = config.providers.get(config.active_provider) if config.providers else None
        if active_prov:
            logger.info("Active provider: %s, model=%s", config.active_provider, active_prov.model)
        else:
            logger.warning("Active provider '%s' not found in DB providers", config.active_provider)
        registry = ProviderRegistry.from_config(config.providers, config.active_provider)
        logger.info("Providers registered: %s", registry.list_providers())
        active_provider = registry.get(config.active_provider)
        tool_registry = create_default_registry(
            timeout=config.tools.max_bash_timeout, provider=active_provider
        )
        _handler = ZenithHandler(
            config=config, db=db, registry=registry, tool_registry=tool_registry
        )
        _test_handler = TestSimulationHandler(workspace_root=config.workspace_root)
        logger.info("Test simulation handler initialized (%s)", TEST_WS_PATH)
        global _mcp_manager
        _mcp_manager = None
        if config.mcp_servers:
            from server.mcp.manager import McpManager

            _mcp_manager = McpManager(config.mcp_servers)
            await _mcp_manager.start()
            for wrapper in _mcp_manager.build_wrappers():
                tool_registry.register(wrapper)
            logger.info(
                "MCP servers ready: %s",
                [
                    {"name": s["name"], "status": s["status"], "tools": s["tools"]}
                    for s in _mcp_manager.list_servers()
                ],
            )
            if _mcp_manager.errors:
                logger.warning("MCP servers with errors: %s", _mcp_manager.errors)
        from server.toolkit.registry_validation import validate_registry

        validation_errors = validate_registry(tool_registry)
        if validation_errors:
            logger.error("Tool registry validation failed at startup:")
            for error in validation_errors:
                logger.error("  %s", error)
        try:
            from server.lsp.manager import LspManager, set_lsp_manager

            lsp_manager = LspManager(workspace_root=config.workspace_root)
            set_lsp_manager(lsp_manager)
            logger.info("LSP manager initialized")
        except Exception as e:
            logger.debug("LSP manager init skipped: %s", e)
        try:
            from server.persistence.repositories import TokenUsageRepository

            pricing_repo = TokenUsageRepository(db)
            await pricing_repo.seed_pricing()
            logger.info("Pricing data seeded")
        except Exception as e:
            logger.warning("Failed to seed pricing data: %s", e)
        _handler.handlers.dispatch = wrap_handler(_handler.handlers.dispatch)
        _shutdown.register_cleanup(db.close)
        logger.info("Handler initialized — server ready")
    except Exception as e:
        logger.error("Startup error encountered: %s", e)
        raise


async def _do_shutdown() -> None:
    global _handler, _shutdown, _mcp_manager, _test_handler
    logger.info("Shutting down Zenith backend...")
    try:
        if _mcp_manager is not None:
            await _mcp_manager.stop()
    finally:
        _mcp_manager = None
        _test_handler = None
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
    db_status = "ok"
    db_version: str | None = None
    if _database is not None:
        db_version = _database.get_current_version()
        if not await _database.health_check():
            db_status = "error"
    return {
        "status": "ok",
        "handler": _handler is not None,
        "version": __version__,
        "db": {"status": db_status, "version": db_version},
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
        "db": {
            "status": "ok" if _database and await _database.health_check() else "error",
            "version": _database.get_current_version() if _database else None,
            "path": _database.db_path if _database else None,
        },
        "mcp": {
            "servers": _mcp_manager.list_servers() if _mcp_manager else [],
            "tools": [
                name for name in _handler.tool_registry.list_tools() if name.startswith("mcp_")
            ],
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


@app.get("/startup/model-selection")
def startup_model_selection_get():
    return get_model_selection()


@app.put("/startup/model-selection")
def startup_model_selection_put(request: ModelStoreRequest):
    try:
        payload = save_model_selection_endpoint(request)
        current = payload.get("current")
        logger.info(
            "model selection saved: current=%s recent=%d favorite=%d",
            (f"{current.get('providerID')}/{current.get('modelID')}" if current else "(none)"),
            len(payload.get("recent", [])),
            len(payload.get("favorite", [])),
        )
        return payload
    except Exception as e:
        logger.warning("Failed to save model selection: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to save model selection: {e}")


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


@app.get("/usage/token-stats")
async def token_usage_stats(since: str | None = None, until: str | None = None):
    if _handler is None:
        return {"models": [], "totals": {}}
    try:
        repo = TokenUsageRepository(_handler.handlers.session_repo.db)
        models = await repo.get_stats_by_model(since=since, until=until)
        totals = await repo.get_total_stats(since=since, until=until)
        return {"models": models, "totals": totals}
    except Exception as e:
        logger.warning("Failed to fetch token stats: %s", e)
        return {"models": [], "totals": {}}


@app.get("/usage/cost-summary")
async def token_cost_summary(period: str = "all"):
    if _handler is None:
        return {"data": []}
    try:
        repo = TokenUsageRepository(_handler.handlers.session_repo.db)
        data = await repo.get_cost_summary(period=period)
        return {"data": data}
    except Exception as e:
        logger.warning("Failed to fetch cost summary: %s", e)
        return {"data": []}


@app.get("/usage/budget/{session_id}")
async def token_budget_status(session_id: str):
    if _handler is None:
        return {"active": False}
    try:
        repo = TokenUsageRepository(_handler.handlers.session_repo.db)
        status = await repo.get_budget_status(session_id)
        return status
    except Exception as e:
        logger.warning("Failed to fetch budget status: %s", e)
        return {"active": False}


@app.post("/usage/budget")
async def token_budget_upsert(data: dict):
    if _handler is None:
        return {"ok": False}
    try:
        repo = TokenUsageRepository(_handler.handlers.session_repo.db)
        await repo.upsert_budget(
            session_id=data["session_id"],
            max_session_cost=float(data.get("max_session_cost", 0)),
            max_daily_cost=float(data.get("max_daily_cost", 0)),
            max_monthly_cost=float(data.get("max_monthly_cost", 0)),
            active=bool(data.get("active", True)),
        )
        return {"ok": True}
    except Exception as e:
        logger.warning("Failed to upsert budget: %s", e)
        return {"ok": False}


@app.get("/usage/steps/{session_id}")
async def token_usage_steps(session_id: str):
    if _handler is None:
        return {"steps": []}
    try:
        repo = TokenUsageRepository(_handler.handlers.session_repo.db)
        steps = await repo.get_per_step_stats(session_id)
        return {"steps": steps}
    except Exception as e:
        logger.warning("Failed to fetch step stats: %s", e)
        return {"steps": []}


@app.get("/usage/efficiency/{session_id}")
async def token_usage_efficiency(session_id: str):
    if _handler is None:
        return {}
    try:
        repo = TokenUsageRepository(_handler.handlers.session_repo.db)
        eff = await repo.get_efficiency(session_id)
        return eff
    except Exception as e:
        logger.warning("Failed to fetch efficiency: %s", e)
        return {}


@app.websocket(WS_PATH)
async def websocket_endpoint(websocket: WebSocket):
    if _handler is None:
        logger.warning("WebSocket rejected: handler not initialized")
        await websocket.close(code=1011, reason="Server not ready")
        return
    origin = websocket.headers.get("origin", "")
    if origin and "localhost" not in origin and ("127.0.0.1" not in origin):
        logger.warning("WebSocket connection from unexpected origin: %s", origin)
    if _WS_TOKEN:
        query_token = websocket.query_params.get("token", "")
        if query_token != _WS_TOKEN:
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


@app.websocket(TEST_WS_PATH)
async def test_websocket_endpoint(websocket: WebSocket):
    if _test_handler is None:
        logger.warning("Test WebSocket rejected: handler not initialized")
        await websocket.close(code=1011, reason="Server not ready")
        return
    origin = websocket.headers.get("origin", "")
    if origin and "localhost" not in origin and ("127.0.0.1" not in origin):
        logger.warning("Test WebSocket connection from unexpected origin: %s", origin)
    if _WS_TOKEN:
        query_token = websocket.query_params.get("token", "")
        if query_token != _WS_TOKEN:
            logger.warning("Test WebSocket rejected: invalid token from %s", websocket.client)
            await websocket.close(code=4001, reason="Invalid auth token")
            return
    logger.info("Test WebSocket connecting from %s", websocket.client)
    await websocket.accept()
    try:
        await _test_handler.handle(websocket)
    except Exception:
        logger.exception("Test WebSocket handler error")
        raise


def create_app() -> FastAPI:
    return app
