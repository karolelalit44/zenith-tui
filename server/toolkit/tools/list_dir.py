from __future__ import annotations

import os
from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    PERMISSION_READ,
    TOOL_DOMAIN_READ,
)

from ..base import BaseTool, ToolResult
from ..path_validator import validate_path


class ListDirTool(BaseTool):
    name = "list_dir"
    description = "List files and subdirectories in a directory"
    requires_mode = None
    capability_id = "workspace_discovery"
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_READ
    domains = (TOOL_DOMAIN_READ,)
    search_terms = (
        "list",
        "dir",
        "ls",
        "tree",
        "directory",
        "files",
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path", "default": "."},
            },
            "required": ["path"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        rel_path = params.get("path") or "."
        try:
            resolved = validate_path(rel_path, workspace_root)
        except ValueError as err:
            return ToolResult(success=False, error=str(err))
        if resolved is None:
            return ToolResult(success=False, error=f"Path escapes workspace boundary: {rel_path}")

        if not resolved.exists():
            return ToolResult(success=False, error=f"Directory not found: {rel_path}")

        if not resolved.is_dir():
            return ToolResult(success=False, error=f"Not a directory: {rel_path}")

        try:
            entries = os.listdir(resolved)
            dirs = [f"{e}/" for e in entries if (resolved / e).is_dir()]
            files = [e for e in entries if (resolved / e).is_file()]
            output_lines = sorted(dirs) + sorted(files)
            output = "\n".join(output_lines)
            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "path": rel_path,
                    "dirs": len(dirs),
                    "files": len(files),
                    "entries": output_lines,
                },
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"Failed to list directory: {exc}")
