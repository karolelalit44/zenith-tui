"""Shared domain enums and types used across the Zenith architecture.

These types are the foundation for all service interfaces and must not
depend on any other backend module (only stdlib and third-party libs).
"""

from enum import Enum, StrEnum


class ScenarioMode(StrEnum):
    """Operating mode for the agent."""
    BUILD = "build"
    PLAN = "plan"


class RiskLevel(StrEnum):
    """Risk level for tool execution and permission requests."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentRole(StrEnum):
    """Role assigned to an agent instance."""
    CODER = "coder"
    TASK = "task"
    REVIEWER = "reviewer"


class AgentState(StrEnum):
    """Lifecycle state of an agent."""
    IDLE = "idle"
    PROCESSING = "processing"
    STREAMING = "streaming"
    TOOL_CALL = "tool_call"
    WAITING = "waiting"
    COMPLETED = "completed"
    ERROR = "error"


class SessionState(StrEnum):
    """Lifecycle state of a session.

    States and transitions:
    CREATED → INITIALIZING → ACTIVE
    ACTIVE → COMPLETED | SUMMARIZED | PAUSED | ERROR | EXPORTED | ARCHIVED | CHECKPOINTING | DRAFT
    INITIALIZING → ACTIVE | ERROR
    COMPLETED → ACTIVE (resume) | SUMMARIZED | EXPORTED | ARCHIVED
    RESUMED → ACTIVE | SUMMARIZED | EXPORTED | ARCHIVED
    SUMMARIZED → RESUMED | ACTIVE | ARCHIVED
    PAUSED → ACTIVE (resume) | ARCHIVED
    ERROR → ACTIVE (retry) | ARCHIVED
    DRAFT → ACTIVE | ARCHIVED
    EXPORTED → ACTIVE | ARCHIVED
    ARCHIVED → _terminal_
    CHECKPOINTING → ACTIVE (transient)
    """
    CREATED = "created"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    RESUMED = "resumed"
    COMPLETED = "completed"
    PAUSED = "paused"
    SUMMARIZED = "summarized"
    EXPORTED = "exported"
    ARCHIVED = "archived"
    DRAFT = "draft"
    ERROR = "error"
    CHECKPOINTING = "checkpointing"


class PermissionDecision(StrEnum):
    """Decision returned by the permission service."""
    ALLOW = "allow"
    DENY = "deny"
    PERSISTENT_ALLOW = "persistent_allow"
    PERSISTENT_DENY = "persistent_deny"


class DeliveryMode(Enum):
    """Event delivery mode for the event bus."""
    LOSSY = "lossy"           # Drop if buffer full (default)
    BLOCKING = "blocking"     # Block until delivered
    PERSISTENT = "persistent" # Store and deliver later


class FinishReason(StrEnum):
    """Why the provider stopped generating."""
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"
