"""Shared domain enums and types used across the Zenith architecture.

These types are the foundation for all service interfaces and must not
depend on any other backend module (only stdlib and third-party libs).
"""

from enum import StrEnum, Enum


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
    """Lifecycle state of a session."""
    CREATED = "created"
    ACTIVE = "active"
    RESUMED = "resumed"
    SUMMARIZED = "summarized"
    EXPORTED = "exported"
    ARCHIVED = "archived"


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
