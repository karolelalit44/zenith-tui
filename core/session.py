"""Session model — represents a conversation session.

A Session tracks:
- Identity and metadata (id, title, mode)
- Lifecycle state (created → active → summarized → archived)
- Parent/child relationships for sub-agents
- Configuration snapshot for the session duration

Backward-compatible with the existing interface.
"""

from __future__ import annotations

import uuid
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Optional

from .domain import ScenarioMode, SessionState


class Session(BaseModel):
    """A conversation session.

    Backward-compatible with the existing interface:
    - id, title, mode (now ScenarioMode), created_at, updated_at,
      workspace_root, is_active, metadata
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "New Session"
    mode: ScenarioMode = ScenarioMode.BUILD
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    workspace_root: str = "."
    is_active: bool = True
    metadata: dict = Field(default_factory=dict)

    # New structured fields
    state: SessionState = SessionState.CREATED
    parent_session_id: Optional[str] = None
    child_session_ids: list[str] = Field(default_factory=list)
    plan_output: str = ""
    plan_approved_at: Optional[datetime] = None
    message_count: int = 0
    total_tokens: int = 0
    model: Optional[str] = None
    provider: Optional[str] = None

    def transition(self, new_state: SessionState) -> None:
        """Transition to a new state with validation."""
        _validate_session_transition(self.state, new_state)
        self.state = new_state
        self.updated_at = datetime.now()

    def archive(self) -> None:
        """Archive the session."""
        self.transition(SessionState.ARCHIVED)
        self.is_active = False

    def add_child(self, child_session_id: str) -> None:
        if child_session_id not in self.child_session_ids:
            self.child_session_ids.append(child_session_id)

    def to_legacy_dict(self) -> dict[str, Any]:
        """Export as legacy dict for backward compatibility."""
        return {
            "id": self.id,
            "title": self.title,
            "mode": self.mode.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "workspace_root": self.workspace_root,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# State machine transitions
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.CREATED: {SessionState.ACTIVE},
    SessionState.ACTIVE: {
        SessionState.ACTIVE,
        SessionState.SUMMARIZED,
        SessionState.EXPORTED,
        SessionState.ARCHIVED,
    },
    SessionState.RESUMED: {
        SessionState.ACTIVE,
        SessionState.SUMMARIZED,
        SessionState.EXPORTED,
        SessionState.ARCHIVED,
    },
    SessionState.SUMMARIZED: {SessionState.RESUMED, SessionState.ARCHIVED},
    SessionState.EXPORTED: {SessionState.ACTIVE, SessionState.ARCHIVED},
    SessionState.ARCHIVED: set(),
}


def _validate_session_transition(current: SessionState, target: SessionState) -> None:
    allowed = _VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(
            f"Invalid session transition: {current.value} → {target.value}. "
            f"Allowed: {', '.join(s.value for s in allowed) or '(none)'}"
        )
