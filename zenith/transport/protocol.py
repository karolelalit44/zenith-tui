from pydantic import BaseModel, Field
from typing import Any, Optional
from zenith.core.events import Event


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


def make_response(request_id: str | int, result: Any) -> str:
    return JsonRpcResponse(id=request_id, result=result).model_dump_json()


def make_error_response(request_id: str | int, code: int, message: str, data: Any = None) -> str:
    return JsonRpcResponse(
        id=request_id, error={"code": code, "message": message, "data": data}
    ).model_dump_json()


def make_event(event: Event) -> str:
    return JsonRpcNotification(params=event.model_dump()).model_dump_json()
