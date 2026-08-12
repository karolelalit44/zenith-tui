from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .domain import ScenarioMode, SessionState


class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "New Session"
    mode: ScenarioMode = ScenarioMode.BUILD
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    workspace_root: str = "."
    is_active: bool = True
    metadata: dict = Field(default_factory=dict)
    state: SessionState = SessionState.CREATED
    parent_session_id: str | None = None
    child_session_ids: list[str] = Field(default_factory=list)
    plan_output: str = ""
    plan_approved_at: datetime | None = None
    message_count: int = 0
    total_tokens: int = 0
    model: str | None = None
    provider: str | None = None
    context_used: int = 0
    context_window: int = 0
    context_percent: float = 0.0
    total_cost: float = 0.0
    error_count: int = 0
    last_error: str | None = None
    agent_state: str = "idle"
    export_format: str | None = None
    exported_at: datetime | None = None

    def transition(self, new_state: SessionState) -> None:
        _validate_session_transition(self.state, new_state)
        self.state = new_state
        self.updated_at = datetime.now()

    def archive(self) -> None:
        self.transition(SessionState.ARCHIVED)
        self.is_active = False

    def add_child(self, child_session_id: str) -> None:
        if child_session_id not in self.child_session_ids:
            self.child_session_ids.append(child_session_id)

    def update_context(self, used: int, window: int) -> None:
        self.context_used = used
        self.context_window = window
        self.context_percent = round(used / window * 100 if window > 0 else 0.0, 2)

    def add_tokens(self, tokens: int, cost: float = 0.0) -> None:
        self.total_tokens += tokens
        self.total_cost += cost

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "mode": self.mode.value,
            "state": self.state.value,
            "provider": self.provider,
            "model": self.model,
            "message_count": self.message_count,
            "total_tokens": self.total_tokens,
            "total_cost": round(self.total_cost, 4),
            "context_percent": self.context_percent,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_active": self.is_active,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "parent_session_id": self.parent_session_id,
        }

    def model_dump_for_db(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "mode": self.mode.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "workspace_root": self.workspace_root,
            "is_active": int(self.is_active),
            "metadata_json": str(self.metadata)
            if isinstance(self.metadata, str)
            else str(__import__("json").dumps(self.metadata)),
            "parent_session_id": self.parent_session_id,
            "state": self.state.value,
            "plan_output": self.plan_output,
            "plan_approved_at": self.plan_approved_at.isoformat()
            if self.plan_approved_at
            else None,
            "context_used": self.context_used,
            "context_window": self.context_window,
            "context_percent": self.context_percent,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "agent_state": self.agent_state,
            "message_count": self.message_count,
            "model": self.model,
            "provider": self.provider,
        }


_VALID_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.CREATED: {
        SessionState.INITIALIZING,
        SessionState.DRAFT,
        SessionState.ACTIVE,
        SessionState.ARCHIVED,
    },
    SessionState.DRAFT: {SessionState.ACTIVE, SessionState.ARCHIVED},
    SessionState.INITIALIZING: {SessionState.ACTIVE, SessionState.ERROR, SessionState.ARCHIVED},
    SessionState.ACTIVE: {
        SessionState.ACTIVE,
        SessionState.COMPLETED,
        SessionState.SUMMARIZED,
        SessionState.PAUSED,
        SessionState.ERROR,
        SessionState.CHECKPOINTING,
        SessionState.EXPORTED,
        SessionState.ARCHIVED,
        SessionState.DRAFT,
    },
    SessionState.COMPLETED: {
        SessionState.ACTIVE,
        SessionState.SUMMARIZED,
        SessionState.EXPORTED,
        SessionState.ARCHIVED,
    },
    SessionState.RESUMED: {
        SessionState.ACTIVE,
        SessionState.COMPLETED,
        SessionState.SUMMARIZED,
        SessionState.EXPORTED,
        SessionState.ARCHIVED,
    },
    SessionState.SUMMARIZED: {SessionState.RESUMED, SessionState.ACTIVE, SessionState.ARCHIVED},
    SessionState.PAUSED: {SessionState.ACTIVE, SessionState.ARCHIVED, SessionState.SUMMARIZED},
    SessionState.ERROR: {SessionState.ACTIVE, SessionState.ARCHIVED, SessionState.EXPORTED},
    SessionState.EXPORTED: {SessionState.ACTIVE, SessionState.ARCHIVED},
    SessionState.CHECKPOINTING: {SessionState.ACTIVE, SessionState.ERROR},
    SessionState.ARCHIVED: set(),
}


def _validate_session_transition(current: SessionState, target: SessionState) -> None:
    allowed = _VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(
            f"Invalid session transition: {current.value} → {target.value}. Allowed: {', '.join(s.value for s in allowed) or '(none)'}"
        )
