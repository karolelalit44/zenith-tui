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
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseTool(ABC):
    """Abstract base class for all tools."""
    name: str = "base"
    description: str = ""
    requires_mode: str | None = None  # None = any, "build", "plan"

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
