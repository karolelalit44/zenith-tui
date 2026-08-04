from __future__ import annotations
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field
from server.domain.events import Event

class JsonRpcMethod(StrEnum):
    SESSION_CREATE = "session.create"
    SESSION_LIST = "session.list"
    SESSION_RESUME = "session.resume"
    SESSION_EXPORT = "session.export"
    SESSION_SEARCH = "session.search"
    PROMPT_SEND = "prompt.send"
    PROMPT_CANCEL = "prompt.cancel"
    PROVIDER_VALIDATE = "provider.validate"
    PROVIDER_MODELS = "provider.models"
    PROVIDER_LIST = "provider.list"
    TOOLS_LIST = "tools.list"
    WORKSPACE_STATUS = "workspace.status"
    WORKSPACE_DIFF = "workspace.diff"
    WORKSPACE_LOG = "workspace.log"
    WORKSPACE_REPO_MAP = "workspace.repo_map"
    PERMISSION_RESPONSE = "permission.response"
    PERMISSION_GRANT = "permission.grant"
    PERMISSION_REVOKE = "permission.revoke"
    PERMISSION_LIST = "permission.list"
    HEALTH = "health"

class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int
    method: str
    params: dict[str, Any] = Field(default_factory=dict)

class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int
    result: Any = None
    error: dict[str, Any] | None = None

class JsonRpcNotification(BaseModel):
    jsonrpc: str = "2.0"
    method: str = "event"
    params: dict[str, Any]

class Connection(BaseModel):
    session_id: str
    client: str = ""

class TransportService(ABC):
    @abstractmethod
    async def start(self, host: str, port: int) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...

    @abstractmethod
    async def broadcast(self, event: Event) -> None:
        ...

    @abstractmethod
    def get_connections(self) -> list[Connection]:
        ...

def make_response(request_id: str | int, result: Any) -> str:
    return JsonRpcResponse(id=request_id, result=result).model_dump_json()

def make_error_response(request_id: str | int, code: int, message: str, data: Any = None) -> str:
    return JsonRpcResponse(id=request_id, error={"code": code, "message": message, "data": data}).model_dump_json()

def make_event(event: Event) -> str:
    return JsonRpcNotification(params=event.model_dump(exclude={"metadata", "parent_event_id"})).model_dump_json()
