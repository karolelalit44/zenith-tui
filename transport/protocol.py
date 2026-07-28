"""JSON-RPC protocol types, method enum, and TransportService ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field

from core.events import Event


# ── JSON-RPC method enum ─────────────────────────────────────────────────

class JsonRpcMethod(StrEnum):
    # Session methods
    SESSION_CREATE = "session.create"
    SESSION_LIST = "session.list"
    SESSION_RESUME = "session.resume"
    SESSION_EXPORT = "session.export"

    # Prompt methods
    PROMPT_SEND = "prompt.send"
    PROMPT_CANCEL = "prompt.cancel"

    # Provider methods
    PROVIDER_VALIDATE = "provider.validate"
    PROVIDER_MODELS = "provider.models"
    PROVIDER_LIST = "provider.list"

    # Tool methods
    TOOLS_LIST = "tools.list"

    # Workspace methods
    WORKSPACE_STATUS = "workspace.status"
    WORKSPACE_DIFF = "workspace.diff"
    WORKSPACE_LOG = "workspace.log"
    WORKSPACE_REPO_MAP = "workspace.repo_map"

    # Permission methods
    PERMISSION_RESPONSE = "permission.response"

    # Health
    HEALTH = "health"


# ── JSON-RPC message types ───────────────────────────────────────────────

class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int
    result: Any = None
    error: Optional[dict[str, Any]] = None


class JsonRpcNotification(BaseModel):
    jsonrpc: str = "2.0"
    method: str = "event"
    params: dict[str, Any]


# ── Connection model ─────────────────────────────────────────────────────

class Connection(BaseModel):
    """Represents an active WebSocket connection."""
    session_id: str
    client: str = ""


# ── Transport service ABC ────────────────────────────────────────────────

class TransportService(ABC):
    """Abstract transport layer — manages connections and event broadcast."""

    @abstractmethod
    async def start(self, host: str, port: int) -> None:
        """Start the transport server."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the transport server."""
        ...

    @abstractmethod
    async def broadcast(self, event: Event) -> None:
        """Broadcast an event to all connected clients."""
        ...

    @abstractmethod
    def get_connections(self) -> list[Connection]:
        """Return a list of active connections."""
        ...


# ── Serialization helpers ────────────────────────────────────────────────

def make_response(request_id: str | int, result: Any) -> str:
    return JsonRpcResponse(id=request_id, result=result).model_dump_json()


def make_error_response(request_id: str | int, code: int, message: str, data: Any = None) -> str:
    return JsonRpcResponse(
        id=request_id, error={"code": code, "message": message, "data": data}
    ).model_dump_json()


def make_event(event: Event) -> str:
    return JsonRpcNotification(params=event.model_dump()).model_dump_json()
