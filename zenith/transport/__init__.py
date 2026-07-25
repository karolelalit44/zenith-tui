import logging
import os
from .server import create_app
from .protocol import JsonRpcRequest, JsonRpcResponse, make_response, make_error_response, make_event
from .websocket import ConnectionManager, ZenithHandler

_log_level = os.getenv("ZENITH_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

__all__ = [
    "create_app",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "make_response",
    "make_error_response",
    "make_event",
    "ConnectionManager",
    "ZenithHandler",
]
