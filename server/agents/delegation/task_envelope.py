"""Task envelope: the mission contract the Captain hands to a specialist.

Also provides the normalized duplicate-detection signature used by the
Repository Intelligence Cache.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid

from pydantic import BaseModel, Field

from .agent_definition import AgentDefinition


class AgentTask(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    capability: str
    objective: str
    scoped_instructions: str = ""
    context_digest: str = ""
    session_id: str
    child_session_id: str | None = None
    parent_task_id: str | None = None
    depth: int = 0
    max_context_tokens: int
    created_at: float = Field(default_factory=time.time)


def build_task_envelope(
    objective: str,
    definition: AgentDefinition,
    session_id: str,
    max_context_tokens: int,
    capability: str | None = None,
    scoped_instructions: str = "",
    context_digest: str = "",
    parent_task_id: str | None = None,
    depth: int = 0,
) -> AgentTask:
    return AgentTask(
        agent_id=definition.id,
        capability=capability or (definition.capabilities[0] if definition.capabilities else ""),
        objective=objective,
        scoped_instructions=scoped_instructions,
        context_digest=context_digest,
        session_id=session_id,
        parent_task_id=parent_task_id,
        depth=depth,
        max_context_tokens=max_context_tokens,
    )


def normalize_objective(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def task_signature(objective: str, agent_id: str, session_id: str) -> str:
    normalized = normalize_objective(objective)
    return hashlib.sha1(f"{normalized}|{agent_id}|{session_id}".encode()).hexdigest()
