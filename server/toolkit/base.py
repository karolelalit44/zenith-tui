from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from server.config.constants import BUILD_MODE


class ToolResult(BaseModel):
    success: bool
    output: str = ""
    error: str = ""
    stop_turn: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolContext(BaseModel):
    request_id: str
    session_id: str | None = None
    workspace_root: str = ""
    mode: str = BUILD_MODE
    tool_name: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolMiddleware(ABC):
    @abstractmethod
    async def before_execute(
        self, name: str, params: dict[str, Any], ctx: ToolContext
    ) -> bool | ToolResult: ...

    async def after_execute(
        self, name: str, params: dict[str, Any], result: ToolResult, ctx: ToolContext
    ) -> ToolResult:
        return result

    async def on_error(
        self, name: str, params: dict[str, Any], error: Exception, ctx: ToolContext
    ) -> ToolResult | None:
        return None


class BaseTool(ABC):
    name: str = "base"
    description: str = ""
    requires_mode: str | None = None

    @property
    def risk_level(self) -> str:
        return "safe"

    @property
    def modes(self) -> list[str] | None:
        if self.requires_mode:
            return [self.requires_mode]
        return None

    @abstractmethod
    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult: ...

    @abstractmethod
    def get_schema(self) -> dict: ...

    def validate_params(self, params: dict[str, Any]) -> bool:
        return True
