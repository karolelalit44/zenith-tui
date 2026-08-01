"""Config-driven PreToolUse / PostToolUse hook middleware (HP-10).

PreToolUse hooks run before tool execution; a non-zero exit code blocks the
tool. PostToolUse hooks run after execution and attach their results to the
ToolResult metadata (they never modify the tool result itself).
"""

from __future__ import annotations

import logging
from typing import Any

from server.domain.hooks import HookRunner

from ..base import ToolContext, ToolMiddleware, ToolResult

logger = logging.getLogger(__name__)


class HookMiddleware(ToolMiddleware):
    """Runs configured PreToolUse/PostToolUse shell hooks around tool calls."""

    def __init__(self, runner: HookRunner | None = None) -> None:
        self._runner = runner or HookRunner()

    async def before_execute(
        self, name: str, params: dict[str, Any], ctx: ToolContext
    ) -> bool | ToolResult:
        if not self._runner.pre_tool_use:
            return True
        results = await self._runner.run_pre_tool_use(
            name,
            params,
            workspace_root=ctx.workspace_root or ".",
            session_id=ctx.session_id,
            mode=ctx.mode,
        )
        for r in results:
            if r["exit_code"] != 0:
                detail = r["stderr"] or r["stdout"]
                msg = (
                    f"Blocked by PreToolUse hook '{r['command']}' "
                    f"(exit {r['exit_code']})"
                )
                if detail:
                    msg += f": {detail[:500]}"
                return ToolResult(success=False, error=msg)
        return True

    async def after_execute(
        self,
        name: str,
        params: dict[str, Any],
        result: ToolResult,
        ctx: ToolContext,
    ) -> ToolResult:
        if not self._runner.post_tool_use:
            return result
        try:
            results = await self._runner.run_post_tool_use(
                name,
                params,
                result,
                workspace_root=ctx.workspace_root or ".",
                session_id=ctx.session_id,
                mode=ctx.mode,
            )
            result.metadata["post_tool_use"] = results
        except Exception as e:
            logger.warning("PostToolUse hook error for '%s': %s", name, e)
        return result
