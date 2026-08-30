from __future__ import annotations

from pathlib import Path
from typing import Any

from server.config.constants import PLAN_MODE

from ..base import ToolContext, ToolMiddleware, ToolResult

PLAN_WRITABLE_FILES = ("plan.md", "todo.md")


def is_plan_write_allowed(workspace_root: str, path: str) -> bool:
    """Plan mode may only write plan.md or todo.md in the workspace root."""
    if not path:
        return False
    try:
        root = Path(workspace_root).resolve()
        target = (root / path).resolve()
    except (OSError, ValueError):
        return False
    if target.parent != root:
        return False
    return target.name in PLAN_WRITABLE_FILES


class PlanWriteGuard(ToolMiddleware):
    """Runtime enforcement of the plan-mode write boundary.

    In plan mode, file_write/file_edit may only target plan.md or todo.md in the
    workspace root. Everything else (source files, config, delete, bash) stays
    outside the plan-mode tool surface, enforced here regardless of the prompt.
    """

    _WRITE_TOOLS = ("file_write", "file_edit")

    async def before_execute(
        self, name: str, params: dict[str, Any], ctx: ToolContext
    ) -> bool | ToolResult:
        if ctx.mode != PLAN_MODE:
            return True
        if name not in self._WRITE_TOOLS:
            return True
        path = params.get("path") or ""
        if not is_plan_write_allowed(ctx.workspace_root, path):
            return ToolResult(
                success=False,
                error=(
                    f"Plan mode only allows writing plan.md or todo.md in the workspace root "
                    f"(got '{path}'). Read files with file_read; write the plan to plan.md/todo.md."
                ),
            )
        return True
