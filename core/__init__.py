"""Core domain types — re-exported for convenient imports.

Usage:
    from core import Event, Message, Session, ScenarioMode
"""

from .domain import (
    ScenarioMode,
    RiskLevel,
    AgentRole,
    AgentState,
    SessionState,
    PermissionDecision,
    DeliveryMode,
    FinishReason,
)
from .events import (
    EventKind,
    Event,
    EventBus,
    AsyncEventBus,
    Subscription,
    make_event,
)
from .message import (
    Message,
    ToolCall,
    ToolResult as MessageToolResult,
)
from .session import Session, SessionState as SessionLifecycle
from .errors import (
    ZenithError,
    ConfigError,
    ProviderError,
    RateLimitError,
    AuthenticationError,
    TimeoutError,
    ModelNotFoundError,
    ToolError,
    ToolPermissionDenied,
    ToolNotFound,
    ToolValidationError,
    SessionError,
    SessionNotFound,
    SessionTransitionError,
    TransportError,
    WebSocketError,
    AgentError,
    MaxIterationsError,
    LoopDetectedError,
    AgentCancelledError,
    LspError,
    LspNotRunning,
    LspTimeout,
    McpError,
    McpNotConnected,
    McpHandshakeFailed,
    PermissionError,
    PermissionDenied,
)

__all__ = [
    # Domain enums
    "ScenarioMode",
    "RiskLevel",
    "AgentRole",
    "AgentState",
    "SessionState",
    "PermissionDecision",
    "DeliveryMode",
    "FinishReason",
    # Events
    "EventKind",
    "Event",
    "EventBus",
    "AsyncEventBus",
    "Subscription",
    "make_event",
    # Messages
    "Message",
    "ToolCall",
    "MessageToolResult",
    # Sessions
    "Session",
    "SessionLifecycle",
    # Errors
    "ZenithError",
    "ConfigError",
    "ProviderError",
    "RateLimitError",
    "AuthenticationError",
    "TimeoutError",
    "ModelNotFoundError",
    "ToolError",
    "ToolPermissionDenied",
    "ToolNotFound",
    "ToolValidationError",
    "SessionError",
    "SessionNotFound",
    "SessionTransitionError",
    "TransportError",
    "WebSocketError",
    "AgentError",
    "MaxIterationsError",
    "LoopDetectedError",
    "AgentCancelledError",
    "LspError",
    "LspNotRunning",
    "LspTimeout",
    "McpError",
    "McpNotConnected",
    "McpHandshakeFailed",
    "PermissionError",
    "PermissionDenied",
]
