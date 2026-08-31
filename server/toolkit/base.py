from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from server.config.constants import (
    BUILD_MODE,
    CONCURRENCY_GROUP_READONLY,
    COST_CLASS_LOW,
    DEFAULT_TOOL_TIMEOUT_MS,
    LATENCY_CLASS_LOW,
    MAX_TOOL_OUTPUT_BASELINE,
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


# ---------------------------------------------------------------------------
# Phase 1 additive — opencode `Tool.Def`-aligned contract (module 03).
# Purely additive: not wired into the legacy path yet; this is the
# interface-locked target that Phase 2 consumers and Phase 3 removals build on.
# ---------------------------------------------------------------------------


class InvalidToolArgumentsError(Exception):
    """Raised when a tool call's arguments fail schema decoding.

    Mirrors opencode's ``InvalidArgumentsError``: the message is fed straight
    back to the model as a "please rewrite input to satisfy the schema" tool
    result, rather than an opaque failure.
    """

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Invalid tool arguments")


class ToolDef:
    """A plain, opencode-style tool definition.

    Equivalent to opencode ``Tool.Def`` ({ id, description, parameters,
    execute }) and codex ``ToolSpec``. Contrast with ``BaseTool``, which carries
    the legacy risk/cost/latency taxonomy this interface-lock replaces.
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any] | None = None,
        execute: Callable[[dict[str, Any], str], Awaitable[ToolResult | str]] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters or {"type": "object", "properties": {}, "required": []}
        self.execute = execute

    def to_schema(self) -> dict[str, Any]:
        """Emit the OpenAI-style tool schema for this definition."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


def decode_parameters(parameters: dict[str, Any] | None, params: dict[str, Any]) -> dict[str, Any]:
    """Decode/validate raw tool args against a JSON-schema-style parameter dict.

    Returns the validated ``params``. Raises ``InvalidToolArgumentsError`` when
    a required property is missing or a disallowed property is present, exactly
    like opencode ``Schema.decodeUnknownEffect`` -> ``InvalidArgumentsError`` fed
    back to the model.
    """
    schema = parameters or {}
    required = schema.get("required") or []
    for key in required:
        if key not in params:
            raise InvalidToolArgumentsError(f"Missing required argument '{key}'")
    if schema.get("additionalProperties", True) is False:
        props = set(schema.get("properties") or {})
        for key in params:
            if key not in props:
                raise InvalidToolArgumentsError(f"Unexpected argument '{key}' not in schema")
    return params


def truncate_output(
    text: str, max_chars: int | None = MAX_TOOL_OUTPUT_BASELINE
) -> tuple[str, bool]:
    """Unified output-truncation service (opencode ``tool/truncate.ts`` intent).

    Truncates ``text`` to ``max_chars`` and returns ``(kept, truncated)`` where
    ``truncated`` is True when content was dropped. Callers that need the full
    payload persist it to a file path and point the model at it, so nothing is
    silently lost. Uses a single limit (not the legacy tier taxonomy).
    """
    if not text:
        return text, False
    if max_chars is None or max_chars < 0 or len(text) <= max_chars:
        return text, False
    marker = "\n... [output truncated; full content available via file_read] ...\n"
    keep = max(0, max_chars - len(marker))
    return text[:keep] + marker, True


@dataclass
class ToolDefResult:
    """Outcome of running a :class:`ToolDef` through :func:`run_tool_def`.

    When ``ok`` is False the ``error`` carries a model-facing rewrite request
    (the ``InvalidToolArgumentsError`` message), so a bad call is fed back as
    "please rewrite input to satisfy the schema" rather than an opaque failure.
    """

    ok: bool
    output: str = ""
    truncated: bool = False
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


async def run_tool_def(
    tool: ToolDef,
    args: dict[str, Any],
    workspace_root: str,
    max_output_chars: int | None = MAX_TOOL_OUTPUT_BASELINE,
) -> ToolDefResult:
    """Resolve and run a :class:`ToolDef` (opencode ``SessionTools.resolve`` intent).

    Decodes/validates ``args`` against the tool's parameter schema; on failure
    returns a model-facing rewrite request (the ``InvalidToolArgumentsError``
    message). Otherwise executes ``tool.execute`` and truncates oversized text
    output through :func:`truncate_output`. Handles both a ``ToolResult`` return
    and a plain-string return.
    """
    try:
        validated = decode_parameters(tool.parameters, args)
    except InvalidToolArgumentsError as exc:
        return ToolDefResult(ok=False, error=str(exc))
    raw = await tool.execute(validated, workspace_root)
    if isinstance(raw, ToolResult):
        kept, truncated = truncate_output(raw.output or "", max_output_chars)
        return ToolDefResult(
            ok=raw.success,
            output=kept,
            truncated=truncated,
            error=raw.error or "",
            metadata=dict(raw.metadata),
        )
    text = str(raw) if raw is not None else ""
    kept, truncated = truncate_output(text, max_output_chars)
    return ToolDefResult(ok=True, output=kept, truncated=truncated)
