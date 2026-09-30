from __future__ import annotations

from typing import Any

from server.config.constants import (
    DISCOVER_CAPABILITIES_TOOL,
    GET_TOOL_DEFINITION_TOOL,
    READ_ONLY_MODE,
)

from ..base import ToolContext, ToolMiddleware, ToolResult
from ..registry import ToolRegistry


class ReadOnlyModeGuard(ToolMiddleware):
    """Reject any mutating tool while in READ_ONLY_MODE.

    Mirrors ``CrewmateReadOnlyGuard`` (which enforces ``CREWMATE_MODE``) but for
    the primary read-only investigation mode. ``tool_choice="none"`` only
    suppresses native tool calls; a text-fenced `````tool```` block or
    ``<tool_call>`` XML bypasses it entirely, so the soft gate alone is
    insufficient. Only tools that announce ``read_only=True`` are permitted at
    execution time.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self.blocked_calls = 0
        self._allowed_cache: frozenset[str] | None = None

    @property
    def allowed(self) -> frozenset[str]:
        """Names permitted in READ_ONLY_MODE.

        Cached because this is consulted on every tool call. The registry is
        populated once during startup and does not change afterwards, so an
        unconditional memo is correct; ``invalidate()`` exists for the case where
        a tool is registered after the middleware is constructed.
        """
        cached = self._allowed_cache
        if cached is None:
            cached = frozenset(
                name
                for name in self._registry.list_tools()
                if getattr(self._registry.get(name), "read_only", False)
            ) | {
                DISCOVER_CAPABILITIES_TOOL,
                GET_TOOL_DEFINITION_TOOL,
            }
            self._allowed_cache = cached
        return cached

    def invalidate(self) -> None:
        """Drop the memoized set so the next access rebuilds it."""
        self._allowed_cache = None

    async def before_execute(
        self, name: str, params: dict[str, Any], ctx: ToolContext
    ) -> bool | ToolResult:
        if ctx.mode != READ_ONLY_MODE:
            return True
        if name == "webfetch" and (params.get("download_path") or params.get("download") or params.get("save_path")):
            self.blocked_calls += 1
            return ToolResult(
                success=False,
                error=(
                    f"Tool '{name}' with download is blocked for {READ_ONLY_MODE} mode: "
                    "investigation is strictly read-only."
                ),
            )
        if name in self.allowed:
            return True
        self.blocked_calls += 1
        return ToolResult(
            success=False,
            error=(
                f"Tool '{name}' is blocked for {READ_ONLY_MODE} mode: "
                "investigation is strictly read-only."
            ),
        )