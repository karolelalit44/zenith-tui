"""Transport module — JSON-RPC protocol, WebSocket server, and connection management."""

import logging
import os
from .server import create_app
from .protocol import (
    JsonRpcMethod,
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcNotification,
    Connection,
    TransportService,
    make_response,
    make_error_response,
    make_event,
)
from .websocket import ConnectionManager, ZenithHandler

_log_level = os.getenv("ZENITH_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,
)

__all__ = [
    # Protocol
    "JsonRpcMethod",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "JsonRpcNotification",
    "Connection",
    "TransportService",
    "make_response",
    "make_error_response",
    "make_event",
    # WebSocket
    "ConnectionManager",
    "ZenithHandler",
    # Server
    "create_app",
]
