from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from server.config.constants import (
    BUILD_MODE,
    CONCURRENCY_GROUP_READONLY,
    COST_CLASS_LOW,
    DEFAULT_TOOL_TIMEOUT_MS,
    LATENCY_CLASS_LOW,
    PERMISSION_READ,
    RISK_SAFE,
)


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

    # Canonical metadata contract (Stage 1: tool orchestration)
    capability_id: str = "core"
    read_only: bool = False
    timeout_ms: int | None = DEFAULT_TOOL_TIMEOUT_MS
    concurrency_group: str = CONCURRENCY_GROUP_READONLY
    permission_scope: str = PERMISSION_READ
    domains: tuple[str, ...] = ()
    search_terms: tuple[str, ...] = ()
    risk_level: str = RISK_SAFE
    cost_class: str = COST_CLASS_LOW
    latency_class: str = LATENCY_CLASS_LOW

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
