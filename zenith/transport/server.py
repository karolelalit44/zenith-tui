"""FastAPI server with graceful lifecycle management."""

from __future__ import annotations

import logging
import os
from fastapi import FastAPI, WebSocket

from .websocket import ZenithHandler
from .shutdown import GracefulShutdown
from .startup import validate_startup, validate_provider_setup, save_provider_setup, get_provider_config, ProviderSetupRequest
from .middleware import wrap_handler
from zenith import __version__
from zenith.config.loader import load_config
from zenith.db.connection import Database, resolve_db_path
from zenith.providers.registry import ProviderRegistry
from zenith.tools import create_default_registry

logger = logging.getLogger(__name__)

# Optional WebSocket auth token — set ZENITH_WS_TOKEN env var to enable
_WS_TOKEN = os.environ.get("ZENITH_WS_TOKEN", "")

_handler: ZenithHandler | None = None
_shutdown: GracefulShutdown | None = None


async def _startup() -> None:
    global _handler, _shutdown
    logger.info("Starting Zenith backend...")

    _shutdown = GracefulShutdown()

    db = Database(resolve_db_path())
    await db.connect()
    logger.info("Database connected")

    from zenith.db.repository import ProviderRepositoryDB
    provider_repo = ProviderRepositoryDB(db)
    await provider_repo.ensure_seeded()

    config = load_config()
    logger.info("Config loaded: provider=%s, db=%s", config.active_provider, config.db_path)

    # Log the active provider's model from DB
    active_prov = config.providers.get(config.active_provider) if config.providers else None
    if active_prov:
        logger.info("Active provider: %s, model=%s", config.active_provider, active_prov.model)
    else:
        logger.warning("Active provider '%s' not found in DB providers", config.active_provider)

    registry = ProviderRegistry.from_config(config.providers, config.active_provider)
    logger.info("Providers registered: %s", registry.list_providers())

    tool_registry = create_default_registry(timeout=config.tools.max_bash_timeout)

    _handler = ZenithHandler(
        config=config, db=db, registry=registry, tool_registry=tool_registry
    )

    # Apply provider validation middleware to WebSocket dispatch
    _handler._dispatch = wrap_handler(_handler._dispatch)

    _shutdown.register_cleanup(db.close)
    logger.info("Handler initialized — server ready")


async def _shutdown_event() -> None:
    global _handler, _shutdown
    logger.info("Shutting down Zenith backend...")
    if _shutdown:
        await _shutdown.shutdown()
    _handler = None
    _shutdown = None
    logger.info("Zenith backend stopped")


app = FastAPI(title="Zenith Backend", version=__version__)
app.add_event_handler("startup", _startup)
app.add_event_handler("shutdown", _shutdown_event)


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
