"""Tool base class — standardized interface for all tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Standardized result from tool execution."""
    success: bool
    output: str = ""
    error: str = ""
    stop_turn: bool = False  # If True, the agent loop should end this turn
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolContext(BaseModel):
    """Immutable context passed to tools during execution."""
    request_id: str
    session_id: str | None = None
    workspace_root: str = ""
    mode: str = "build"  # "build" | "plan"
    tool_name: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolMiddleware(ABC):
    """Middleware that intercepts tool execution for cross-cutting concerns."""

    @abstractmethod
    async def before_execute(
        self, name: str, params: dict[str, Any], ctx: ToolContext
    ) -> bool | ToolResult:
        """Run before tool execution.

        Return True to proceed, or a ToolResult to short-circuit.
        """
        ...

    async def after_execute(
        self,
        name: str,
        params: dict[str, Any],
        result: ToolResult,
        ctx: ToolContext,
    ) -> ToolResult:
        """Run after tool execution. Returns (possibly modified) result."""
        return result

    async def on_error(
        self,
        name: str,
        params: dict[str, Any],
        error: Exception,
        ctx: ToolContext,
    ) -> ToolResult | None:
        """Run when tool raises. Return a ToolResult to suppress the error, or None to propagate."""
        return None


class BaseTool(ABC):
    """Abstract base class for all tools."""
    name: str = "base"
    description: str = ""
    requires_mode: str | None = None  # Legacy — prefer `modes`

    @property
    def risk_level(self) -> str:
        """Risk classification: 'safe', 'low', 'medium', 'high'."""
        return "safe"

    @property
    def modes(self) -> list[str] | None:
        """Which modes this tool is available in, or None for any."""
        if self.requires_mode:
            return [self.requires_mode]
        return None

    @abstractmethod
    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        """Execute the tool with given parameters."""
        ...

    @abstractmethod
    def get_schema(self) -> dict:
        """Return JSON schema for tool parameters."""
        ...

    def validate_params(self, params: dict[str, Any]) -> bool:
        """Validate parameters before execution. Override for custom validation."""
        return True
