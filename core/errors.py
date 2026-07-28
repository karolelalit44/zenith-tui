"""Exception hierarchy — typed errors for every domain.

Every ZenithError carries:
- message: human-readable description
- code: machine-readable string for client dispatch
- recoverable: whether the caller should retry
- cause: optional chained exception

The hierarchy follows:
    ZenithError
    ├── ConfigError
    ├── ProviderError
    │   ├── RateLimitError
    │   ├── AuthenticationError
    │   ├── TimeoutError
    │   └── ModelNotFoundError
    ├── ToolError
    │   ├── ToolPermissionDenied
    │   ├── ToolNotFound
    │   └── ToolValidationError
    ├── SessionError
    │   ├── SessionNotFound
    │   └── SessionTransitionError
    ├── TransportError
    │   └── WebSocketError
    ├── AgentError
    │   ├── MaxIterationsError
    │   ├── LoopDetectedError
    │   └── AgentCancelledError
    ├── LspError
    │   ├── LspNotRunning
    │   └── LspTimeout
    ├── McpError
    │   ├── McpNotConnected
    │   └── McpHandshakeFailed
    └── PermissionError
        └── PermissionDenied
"""

from __future__ import annotations


class ZenithError(Exception):
    """Base exception for all Zenith errors."""

    def __init__(
        self,
        message: str,
        code: str = "UNKNOWN",
        recoverable: bool = False,
        cause: Exception | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable
        self.cause = cause

    def to_dict(self) -> dict:
        return {
            "error": str(self),
            "code": self.code,
            "recoverable": self.recoverable,
        }


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class ConfigError(ZenithError):
    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message, code="CONFIG_ERROR", recoverable=False, cause=cause)


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class ProviderError(ZenithError):
    def __init__(self, message: str, provider: str = "", recoverable: bool = True, cause: Exception | None = None):
        super().__init__(message, code="PROVIDER_ERROR", recoverable=recoverable, cause=cause)
        self.provider = provider


class RateLimitError(ProviderError):
    def __init__(self, message: str = "Rate limit exceeded", provider: str = "", retry_after: float | None = None):
        super().__init__(message, provider=provider, recoverable=True)
        self.code = "RATE_LIMIT"
        self.retry_after = retry_after


class AuthenticationError(ProviderError):
    def __init__(self, message: str = "Authentication failed", provider: str = ""):
        super().__init__(message, provider=provider, recoverable=False)
        self.code = "AUTH_ERROR"


class TimeoutError(ProviderError):
    def __init__(self, message: str = "Request timed out", provider: str = "", timeout: float | None = None):
        super().__init__(message, provider=provider, recoverable=True)
        self.code = "TIMEOUT"
        self.timeout = timeout


class ModelNotFoundError(ProviderError):
    def __init__(self, model: str, provider: str = ""):
        super().__init__(f"Model '{model}' not found", provider=provider, recoverable=False)
        self.code = "MODEL_NOT_FOUND"
        self.model = model


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class ToolError(ZenithError):
    def __init__(self, message: str, tool: str = "", recoverable: bool = True, cause: Exception | None = None):
        super().__init__(message, code="TOOL_ERROR", recoverable=recoverable, cause=cause)
        self.tool = tool


class ToolPermissionDenied(ToolError):
    def __init__(self, tool: str, reason: str = "Permission denied"):
        super().__init__(reason, tool=tool, recoverable=False)
        self.code = "TOOL_PERMISSION_DENIED"


class ToolNotFound(ToolError):
    def __init__(self, tool: str):
        super().__init__(f"Tool '{tool}' not found", tool=tool, recoverable=False)
        self.code = "TOOL_NOT_FOUND"


class ToolValidationError(ToolError):
    def __init__(self, tool: str, detail: str):
        super().__init__(f"Validation failed for '{tool}': {detail}", tool=tool, recoverable=False)
        self.code = "TOOL_VALIDATION"


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class SessionError(ZenithError):
    def __init__(self, message: str, session_id: str = "", cause: Exception | None = None):
        super().__init__(message, code="SESSION_ERROR", recoverable=False, cause=cause)
        self.session_id = session_id


class SessionNotFound(SessionError):
    def __init__(self, session_id: str):
        super().__init__(f"Session '{session_id}' not found", session_id=session_id)
        self.code = "SESSION_NOT_FOUND"


class SessionTransitionError(SessionError):
    def __init__(self, session_id: str, from_state: str, to_state: str):
        super().__init__(
            f"Invalid session transition: {from_state} → {to_state}",
            session_id=session_id,
        )
        self.code = "SESSION_TRANSITION"
        self.from_state = from_state
        self.to_state = to_state


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

class TransportError(ZenithError):
    def __init__(self, message: str, recoverable: bool = True, cause: Exception | None = None):
        super().__init__(message, code="TRANSPORT_ERROR", recoverable=recoverable, cause=cause)


class WebSocketError(TransportError):
    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message, recoverable=True, cause=cause)
        self.code = "WEBSOCKET_ERROR"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class AgentError(ZenithError):
    def __init__(self, message: str, session_id: str = "", recoverable: bool = False, cause: Exception | None = None):
        super().__init__(message, code="AGENT_ERROR", recoverable=recoverable, cause=cause)
        self.session_id = session_id


class MaxIterationsError(AgentError):
    def __init__(self, max_iter: int, session_id: str = ""):
        super().__init__(f"Max iterations ({max_iter}) exceeded", session_id=session_id)
        self.code = "MAX_ITERATIONS"
        self.max_iter = max_iter


class LoopDetectedError(AgentError):
    def __init__(self, hash: str, session_id: str = ""):
        super().__init__(f"Loop detected (hash={hash})", session_id=session_id)
        self.code = "LOOP_DETECTED"
        self.hash = hash


class AgentCancelledError(AgentError):
    def __init__(self, session_id: str = ""):
        super().__init__("Agent cancelled by user", session_id=session_id, recoverable=True)
        self.code = "AGENT_CANCELLED"


# ---------------------------------------------------------------------------
# LSP
# ---------------------------------------------------------------------------

class LspError(ZenithError):
    def __init__(self, message: str, language: str = "", cause: Exception | None = None):
        super().__init__(message, code="LSP_ERROR", recoverable=True, cause=cause)
        self.language = language


class LspNotRunning(LspError):
    def __init__(self, language: str = ""):
        super().__init__(f"LSP server not running for '{language}'", language=language)
        self.code = "LSP_NOT_RUNNING"


class LspTimeout(LspError):
    def __init__(self, language: str = "", operation: str = ""):
        super().__init__(f"LSP timeout: {operation} for '{language}'", language=language)
        self.code = "LSP_TIMEOUT"


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------

class McpError(ZenithError):
    def __init__(self, message: str, server: str = "", cause: Exception | None = None):
        super().__init__(message, code="MCP_ERROR", recoverable=True, cause=cause)
        self.server = server


class McpNotConnected(McpError):
    def __init__(self, server: str = ""):
        super().__init__(f"MCP server not connected: '{server}'", server=server)
        self.code = "MCP_NOT_CONNECTED"


class McpHandshakeFailed(McpError):
    def __init__(self, server: str = "", detail: str = ""):
        super().__init__(f"MCP handshake failed for '{server}': {detail}", server=server)
        self.code = "MCP_HANDSHAKE_FAILED"


# ---------------------------------------------------------------------------
# Permission
# ---------------------------------------------------------------------------

class PermissionError(ZenithError):
    def __init__(self, message: str, tool: str = "", recoverable: bool = False):
        super().__init__(message, code="PERMISSION_ERROR", recoverable=recoverable)
        self.tool = tool


class PermissionDenied(PermissionError):
    def __init__(self, tool: str, reason: str = "Permission denied"):
        super().__init__(reason, tool=tool, recoverable=False)
        self.code = "PERMISSION_DENIED"
