import time
import uuid
from pydantic import BaseModel, Field
from typing import Any, Optional
from enum import Enum


class EventKind(str, Enum):
    THINKING = "thinking"
    FILE_CREATE = "file_create"
    FILE_EDIT = "file_edit"
    FILE_DELETE = "file_delete"
    TERMINAL = "terminal"
    ERROR = "error"
    WARNING = "warning"
    RETRY = "retry"
    SUCCESS = "success"
    SUMMARY = "summary"
    MESSAGE = "message"
    PROGRESS = "progress"
    WAITING = "waiting"
    TEST_EXECUTION = "test_execution"
    BUILD_STEP = "build_step"
    DEPLOYMENT = "deployment"
    ANALYSIS = "analysis"
    PLANNER_ACTION_PANEL = "planner_action_panel"
    MODE_MISMATCH = "mode_mismatch"
    PERMISSION_REQUEST = "permission_request"


class Event(BaseModel):
    kind: EventKind
    id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    session_id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    data: dict[str, Any] = Field(default_factory=dict)


def make_event(kind: EventKind, data: dict[str, Any], session_id: str | None = None) -> Event:
    return Event(kind=kind, data=data, session_id=session_id)
