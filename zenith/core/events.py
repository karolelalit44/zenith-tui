import time
import uuid
from pydantic import BaseModel, Field
from typing import Any, Optional
from enum import StrEnum


class EventKind(StrEnum):
    THINKING = "thinking"
    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    WARNING = "warning"
    SUCCESS = "success"
    PROGRESS = "progress"
    CONFIRMATION_REQUEST = "confirmation_request"


class Event(BaseModel):
    kind: EventKind
    id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    session_id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    data: dict[str, Any] = Field(default_factory=dict)


def make_event(kind: EventKind, data: dict[str, Any], session_id: str | None = None) -> Event:
    return Event(kind=kind, data=data, session_id=session_id)
