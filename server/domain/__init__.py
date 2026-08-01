"""Core domain types — re-exported for convenient imports.

Usage:
    from server.domain import Event, Message, Session, ScenarioMode
"""

from .domain import (
    AgentRole,
    AgentState,
    DeliveryMode,
    FinishReason,
    PermissionDecision,
    RiskLevel,
    ScenarioMode,
    SessionState,
)
from .errors import (
    AgentCancelledError,
    AgentError,
    AuthenticationError,
    ConfigError,
    LoopDetectedError,
    LspError,
    LspNotRunning,
    LspTimeout,
    MaxIterationsError,
    McpError,
    McpHandshakeFailed,
    McpNotConnected,
    ModelNotFoundError,
    PermissionDenied,
    PermissionError,
    ProviderError,
    RateLimitError,
    SessionError,
    SessionNotFound,
    SessionTransitionError,
    TimeoutError,
    ToolError,
    ToolNotFound,
    ToolPermissionDenied,
    ToolValidationError,
    TransportError,
    WebSocketError,
    ZenithError,
)
from .events import (
    AsyncEventBus,
    Event,
    EventBus,
    EventKind,
    Subscription,
    make_event,
)
from .message import (
    Message,
    ToolCall,
)
from .message import (
    ToolResult as MessageToolResult,
)
from .session import Session
from .session import SessionState as SessionLifecycle

__all__ = [
    "AgentCancelledError",
    "AgentError",
    "AgentRole",
    "AgentState",
    "AsyncEventBus",
    "AuthenticationError",
    "ConfigError",
    "DeliveryMode",
    "Event",
    "EventBus",
    # Events
    "EventKind",
    "FinishReason",
    "LoopDetectedError",
    "LspError",
    "LspNotRunning",
    "LspTimeout",
    "MaxIterationsError",
    "McpError",
    "McpHandshakeFailed",
    "McpNotConnected",
    # Messages
    "Message",
    "MessageToolResult",
    "ModelNotFoundError",
    "PermissionDecision",
    "PermissionDenied",
    "PermissionError",
    "ProviderError",
    "RateLimitError",
    "RiskLevel",
    # Domain enums
    "ScenarioMode",
    # Sessions
    "Session",
    "SessionError",
    "SessionLifecycle",
    "SessionNotFound",
    "SessionState",
    "SessionTransitionError",
    "Subscription",
    "TimeoutError",
    "ToolCall",
    "ToolError",
    "ToolNotFound",
    "ToolPermissionDenied",
    "ToolValidationError",
    "TransportError",
    "WebSocketError",
    # Errors
    "ZenithError",
    "make_event",
]
