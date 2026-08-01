"""Validation middleware — validates tool parameters before execution."""

from __future__ import annotations

from typing import Any

from ..base import ToolContext, ToolMiddleware, ToolResult


class ValidationMiddleware(ToolMiddleware):
    """Rejects execution when required parameters are missing or empty."""

    # Per-tool required parameter lists (extend as needed)
    _REQUIRED: dict[str, list[str]] = {
        "bash": ["command"],
        "file_write": ["path", "content"],
        "file_edit": ["path", "old", "new"],
        "file_read": ["path"],
        "file_delete": ["path"],
        "glob": ["pattern"],
        "grep": ["pattern"],
    }

    async def before_execute(
        self, name: str, params: dict[str, Any], ctx: ToolContext
    ) -> bool | ToolResult:
        required = self._REQUIRED.get(name)
        if not required:
            return True

        missing = [k for k in required if not params.get(k)]
        if missing:
            return ToolResult(
                success=False,
                error=f"Missing required parameters for '{name}': {', '.join(missing)}",
            )

        return True
