from enum import Enum, StrEnum

from server.config.constants import BUILD_MODE, PLAN_MODE


class ScenarioMode(StrEnum):
    BUILD = BUILD_MODE
    PLAN = PLAN_MODE


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentRole(StrEnum):
    CODER = "coder"
    TASK = "task"
    REVIEWER = "reviewer"


class AgentState(StrEnum):
    IDLE = "idle"
    PROCESSING = "processing"
    STREAMING = "streaming"
    TOOL_CALL = "tool_call"
    WAITING = "waiting"
    COMPLETED = "completed"
    ERROR = "error"


class SessionState(StrEnum):
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
    ALLOW = "allow"
    DENY = "deny"
    PERSISTENT_ALLOW = "persistent_allow"
    PERSISTENT_DENY = "persistent_deny"


class DeliveryMode(Enum):
    LOSSY = "lossy"
    BLOCKING = "blocking"
    PERSISTENT = "persistent"


class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"
