from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from server.config.constants import (
    BUILD_MODE,
    CONCURRENCY_GROUP_WORKSPACE_MUTATION,
    PERMISSION_DELETE,
    RISK_MEDIUM,
    TOOL_DOMAIN_EDIT,
)
from server.workspace.ignore import blocked_as_missing, get_matcher

from ..base import BaseTool, ToolResult
from ..path_validator import validate_path


def _count_entries(root: Path) -> int:
    """Count files and directories under a tree (for a useful delete summary)."""
    count = 0
    for _ in root.rglob("*"):
        count += 1
    return count


class FileDeleteTool(BaseTool):
    name = "file_delete"
    description = "Delete a file or a directory tree (recursively)."
    requires_mode = BUILD_MODE
    capability_id = "file_delete"
    read_only = False
    concurrency_group = CONCURRENCY_GROUP_WORKSPACE_MUTATION
    permission_scope = PERMISSION_DELETE
    domains = (TOOL_DOMAIN_EDIT,)
    search_terms = (
        "delete",
        "remove",
        "unlink",
        "clean up",
    )
    risk_level = RISK_MEDIUM

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File or directory path to delete"}
            },
            "required": ["path"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        rel_path = params.get("path", "")
        resolved = validate_path(rel_path, workspace_root)
        if resolved is None:
            return ToolResult(success=False, error=f"Path escapes workspace boundary: {rel_path}")
        if blocked_as_missing(get_matcher(workspace_root), rel_path):
            return ToolResult(success=False, error=f"Not found: {rel_path}")
        if not resolved.exists():
            return ToolResult(success=False, error=f"Not found: {rel_path}")
        try:
            if resolved.is_dir():
                removed = _count_entries(resolved)
                shutil.rmtree(resolved)
                return ToolResult(
                    success=True,
                    output=f"Deleted directory '{rel_path}' ({removed} entries)",
                    metadata={"path": str(resolved), "directory": True, "entries": removed},
                )
            content = ""
            try:
                content = resolved.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
            resolved.unlink()
            return ToolResult(
                success=True,
                output=f"Deleted {rel_path}",
                metadata={"path": str(resolved), "content": content},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
