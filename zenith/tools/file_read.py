"""File read tool — read file contents with line numbers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseTool, ToolResult
from .param_normalizer import normalize_file_params


class FileReadTool(BaseTool):
    name = "file_read"
    description = "Read the contents of a file"
    requires_mode = None  # Available in both plan and build

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start from (0-indexed, default: 0)",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read (default: 2000)",
                    "default": 2000,
                },
            },
            "required": ["path"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        params = normalize_file_params(params)
        rel_path = params.get("path") or ""
        path = Path(workspace_root) / rel_path
        offset = params.get("offset", 0)
        limit = params.get("limit", 2000)

        if not path.exists():
            return ToolResult(success=False, error=f"File not found: {path}")

        if path.is_dir():
            return ToolResult(success=False, error=f"Path is a directory: {path}")

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            lines = content.split("\n")
            selected = lines[offset : offset + limit]
            numbered = "\n".join(
                f"{i + offset + 1}: {line}" for i, line in enumerate(selected)
            )
            return ToolResult(
                success=True,
                output=numbered,
                metadata={
                    "total_lines": len(lines),
                    "showing": len(selected),
                    "path": str(path),
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
