from __future__ import annotations

from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    MAX_FILE_READ_LINES,
    PERMISSION_READ,
    TOOL_DOMAIN_READ,
)

from ..base import BaseTool, ToolResult
from ..path_validator import validate_path


class FileReadTool(BaseTool):
    name = "file_read"
    description = "Read file contents"
    requires_mode = None
    capability_id = "file_read"
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_READ
    domains = (TOOL_DOMAIN_READ,)
    search_terms = (
        "read",
        "view",
        "cat",
        "inspect",
        "open file",
        "contents",
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "offset": {
                    "type": "integer",
                    "description": "Start line (0-indexed)",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max lines (capped)",
                    "default": MAX_FILE_READ_LINES,
                },
            },
            "required": ["path"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        rel_path = params.get("path") or ""
        resolved = validate_path(rel_path, workspace_root)
        if resolved is None:
            return ToolResult(success=False, error=f"Path escapes workspace boundary: {rel_path}")
        offset = params.get("offset", 0)
        limit = min(int(params.get("limit", MAX_FILE_READ_LINES)), MAX_FILE_READ_LINES)
        if not resolved.exists():
            return ToolResult(success=False, error=f"File not found: {rel_path}")
        if resolved.is_dir():
            return ToolResult(success=False, error=f"Path is a directory: {rel_path}")
        try:
            content = resolved.read_text(encoding="utf-8", errors="replace")
            lines = content.split("\n")
            selected = lines[offset : offset + limit]
            numbered = "\n".join((f"{i + offset + 1}: {line}" for i, line in enumerate(selected)))
            return ToolResult(
                success=True,
                output=numbered,
                metadata={
                    "total_lines": len(lines),
                    "showing": len(selected),
                    "path": str(resolved),
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
