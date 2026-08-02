"""Transport module — JSON-RPC protocol, WebSocket server, and connection management."""

import logging
import os

from .protocol import (
    Connection,
    JsonRpcMethod,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    TransportService,
    make_error_response,
    make_event,
    make_response,
)
from .server import create_app
from .websocket import ConnectionManager, ZenithHandler

_log_level = os.getenv("ZENITH_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("zenith_server.log", mode="w"),
    ],
    force=True,
)

# Silence noisy third-party loggers
for _noisy in ("aiosqlite", "sqlalchemy.engine", "sqlalchemy.engine.Engine", "LiteLLM"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

__all__ = [
    "Connection",
    # WebSocket
    "ConnectionManager",
    # Protocol
    "JsonRpcMethod",
    "JsonRpcNotification",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "TransportService",
    "ZenithHandler",
    # Server
    "create_app",
    "make_error_response",
    "make_event",
    "make_response",
]
