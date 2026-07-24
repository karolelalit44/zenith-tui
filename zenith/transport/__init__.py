import logging
from .server import create_app
from .protocol import JsonRpcRequest, JsonRpcResponse, make_response, make_error_response, make_event
from .websocket import ConnectionManager, ZenithHandler

logging.basicConfig(
    level=logging.INFO,
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
