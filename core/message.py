"""Message model — structured representation of conversation messages.

A Message represents a single turn in a conversation. It can contain:
- Plain text content (for user/assistant messages)
- Tool calls (when the assistant requests tool execution)
- Tool results (output from tool execution)

Messages are immutable once created. Use Message.model_copy() to create
modified versions.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .events import Event


class ToolCall(BaseModel):
    """A structured tool call from the LLM."""
    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:12]}")
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    raw_arguments: str = ""  # Original JSON string before parsing


class ToolResult(BaseModel):
    """Result of a tool execution."""
    tool_call_id: str
    success: bool
    output: str = ""
    error: str = ""
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    """A single message in a conversation.

    Backward-compatible with the existing interface:
    - session_id, role, content, events, token_count, created_at, metadata
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    role: str  # "system", "user", "assistant", "tool"
    content: str = ""
    events: list[Event] = Field(default_factory=list)
    token_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # New structured fields for tool calls
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_result: ToolResult | None = None
    parent_message_id: str | None = None

    @property
    def is_tool_message(self) -> bool:
        return self.role == "tool"

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    def get_tool_call_by_id(self, call_id: str) -> ToolCall | None:
        for tc in self.tool_calls:
            if tc.id == call_id:
                return tc
        return None
