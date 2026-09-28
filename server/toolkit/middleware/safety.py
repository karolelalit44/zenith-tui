from __future__ import annotations

from typing import Any

from server.config.constants import BASH_TOOL, TERMINAL_TOOL

from ..base import ToolContext, ToolMiddleware, ToolResult
from ..command_safety import assess_command

_SHELL_TOOLS = (BASH_TOOL, TERMINAL_TOOL)


class SafetyCheckMiddleware(ToolMiddleware):
    """Hard-block destructive shell commands.

    This is the only execution rule in the module: Zenith has no permission
    tiers and no approval flow, so a command is either blocked outright or it
    runs. Refusal is name/pattern-based, not a sandbox.
    """

    async def before_execute(
        self, name: str, params: dict[str, Any], ctx: ToolContext
    ) -> bool | ToolResult:
        if name not in _SHELL_TOOLS:
            return True
        command = params.get("command", "")
        if not command:
            return True
        assessment = assess_command(command)
        if assessment.is_destructive:
            return ToolResult(
                success=False, error=f"Command blocked by safety policy: {assessment.reason}"
            )
        return True
