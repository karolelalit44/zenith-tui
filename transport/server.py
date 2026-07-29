"""FastAPI server with graceful lifecycle management."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from importlib.metadata import version as _get_version

from fastapi import FastAPI, WebSocket

from db.repository import TokenUsageRepository

from .middleware import wrap_handler
from .shutdown import GracefulShutdown
from .startup import (
    ProviderSetupRequest,
    get_provider_config,
    save_provider_setup,
    validate_provider_setup,
    validate_startup,
)
from .websocket import ZenithHandler

try:
    __version__ = _get_version("zenith")
except Exception:
    __version__ = "0.1.0"
from config.loader import load_config
from db.connection import Database, resolve_db_path
from providers.registry import ProviderRegistry
from tools import create_default_registry

logger = logging.getLogger(__name__)

# Optional WebSocket auth token — set ZENITH_WS_TOKEN env var to enable
_WS_TOKEN = os.environ.get("ZENITH_WS_TOKEN", "")

_handler: ZenithHandler | None = None
_shutdown: GracefulShutdown | None = None


async def _do_startup() -> None:
    global _handler, _shutdown
    logger.info("Starting Zenith backend...")

    _shutdown = GracefulShutdown()

    db = Database(resolve_db_path())
    await db.connect()
    logger.info("Database connected")

    from db.repository import ProviderRepositoryDB
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
        timeout=config.tools.max_bash_timeout,
        provider=active_provider,
    )

    _handler = ZenithHandler(
        config=config, db=db, registry=registry, tool_registry=tool_registry
    )

    try:
        from lsp.manager import LspManager, set_lsp_manager
        lsp_manager = LspManager(workspace_root=config.workspace_root)
        set_lsp_manager(lsp_manager)
        logger.info("LSP manager initialized")
    except Exception as e:
        logger.debug("LSP manager init skipped: %s", e)

    try:
        from db.repository import TokenUsageRepository
        pricing_repo = TokenUsageRepository(db)
        await pricing_repo.seed_pricing()
        logger.info("Pricing data seeded")
    except Exception as e:
        logger.warning("Failed to seed pricing data: %s", e)

    _handler.handlers.dispatch = wrap_handler(_handler.handlers.dispatch)

    _shutdown.register_cleanup(db.close)
    logger.info("Handler initialized — server ready")


async def _do_shutdown() -> None:
    global _handler, _shutdown
    logger.info("Shutting down Zenith backend...")
    if _shutdown:
        await _shutdown.shutdown()
    _handler = None
    _shutdown = None
    logger.info("Zenith backend stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _do_startup()
    yield
    await _do_shutdown()


app = FastAPI(title="Zenith Backend", version=__version__, lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "handler": _handler is not None,
        "version": __version__,
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
    }


@app.get("/startup/validate")
async def startup_validate():
    result = validate_startup()
    return result.model_dump()


@app.post("/startup/validate-provider")
async def startup_validate_provider(request: ProviderSetupRequest):
    result = await validate_provider_setup(request)
    return result.model_dump()


@app.post("/startup/save-config")
async def startup_save_config(request: ProviderSetupRequest):
    result = save_provider_setup(request)
    if result.valid and _handler is not None:
        _handler._reload_config()
        logger.info(
            "Handler config reloaded: provider=%s, providers=%s",
            _handler.config.active_provider,
            list((_handler.config.providers or {}).keys()),
        )
    return result.model_dump()


@app.get("/startup/provider-config")
async def startup_provider_config():
    result = get_provider_config()
    return result.model_dump()


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


@app.get("/usage/token-stats/{session_id}")
async def token_usage_session(session_id: str):
    if _handler is None:
        return {"usage": []}
    try:
        repo = TokenUsageRepository(_handler.handlers.session_repo.db)
        usage = await repo.get_session_token_usage(session_id)
        return {"usage": usage}
    except Exception as e:
        logger.warning("Failed to fetch session token usage: %s", e)
        return {"usage": []}


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


@app.post("/usage/seed-pricing")
async def seed_pricing():
    if _handler is None:
        return {"ok": False}
    try:
        repo = TokenUsageRepository(_handler.handlers.session_repo.db)
        await repo.seed_pricing()
        return {"ok": True}
    except Exception as e:
        logger.warning("Failed to seed pricing: %s", e)
        return {"ok": False}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if _handler is None:
        logger.warning("WebSocket rejected: handler not initialized")
        await websocket.close(code=1011, reason="Server not ready")
        return

    # Optional origin validation
    origin = websocket.headers.get("origin", "")
    if origin and "localhost" not in origin and "127.0.0.1" not in origin:
        logger.warning("WebSocket connection from unexpected origin: %s", origin)

    # Optional token-based auth via query param: ws://host/ws?token=...
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
    except Exception as e:
        logger.exception("WebSocket handler error: %s", e)


def create_app() -> FastAPI:
    return app
