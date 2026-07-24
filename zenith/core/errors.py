class ZenithError(Exception):
    def __init__(self, message: str, code: str = "UNKNOWN", recoverable: bool = False):
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable


class ConfigError(ZenithError):
    def __init__(self, message: str):
        super().__init__(message, code="CONFIG_ERROR", recoverable=False)


class ProviderError(ZenithError):
    def __init__(self, message: str, provider: str = "", recoverable: bool = True):
        super().__init__(message, code="PROVIDER_ERROR", recoverable=recoverable)
        self.provider = provider


class ToolError(ZenithError):
    def __init__(self, message: str, tool: str = "", recoverable: bool = True):
        super().__init__(message, code="TOOL_ERROR", recoverable=recoverable)
        self.tool = tool


class SessionError(ZenithError):
    def __init__(self, message: str):
        super().__init__(message, code="SESSION_ERROR", recoverable=False)


class TransportError(ZenithError):
    def __init__(self, message: str):
        super().__init__(message, code="TRANSPORT_ERROR", recoverable=True)


class PermissionDenied(ZenithError):
    def __init__(self, tool: str):
        super().__init__(f"Permission denied for tool: {tool}", code="PERMISSION_DENIED", recoverable=False)
        self.tool = tool


class MaxIterationsError(ZenithError):
    def __init__(self, max_iter: int):
        super().__init__(f"Max iterations ({max_iter}) exceeded", code="MAX_ITERATIONS", recoverable=False)


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
