from __future__ import annotations

from typing import Any

from ..base import ToolContext, ToolMiddleware, ToolResult
from ..command_safety import assess_command


class SafetyCheckMiddleware(ToolMiddleware):
    async def before_execute(
        self, name: str, params: dict[str, Any], ctx: ToolContext
    ) -> bool | ToolResult:
        if name != "bash":
            return True
        command = params.get("command", "")
        if not command:
            return True
        assessment = assess_command(command)
        if assessment.is_risky and assessment.risk_level == "high":
            return ToolResult(
                success=False, error=f"Command blocked by safety policy: {assessment.reason}"
            )
        return True
