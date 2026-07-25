"""File delete tool — remove files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseTool, ToolResult


class FileDeleteTool(BaseTool):
    name = "file_delete"
    description = "Delete a file"
    requires_mode = "build"

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to delete",
                },
            },
            "required": ["path"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        path = Path(workspace_root) / params.get("path", "")

        if not path.exists():
            return ToolResult(success=False, error=f"File not found: {path}")

        if path.is_dir():
            return ToolResult(
                success=False,
                error=f"Cannot delete directory with file_delete: {path}",
            )

        try:
            path.unlink()
            return ToolResult(
                success=True,
                output=f"Deleted {path}",
                metadata={"path": str(path)},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
