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
