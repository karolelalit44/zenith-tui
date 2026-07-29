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
    force=True,
)

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
