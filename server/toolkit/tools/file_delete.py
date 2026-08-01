"""File delete tool — remove files."""

from __future__ import annotations

from typing import Any

from .base import BaseTool, ToolResult
from .path_validator import validate_path


class FileDeleteTool(BaseTool):
    name = "file_delete"
    description = "Delete a file"
    requires_mode = "build"

    @property
    def risk_level(self) -> str:
        return "medium"

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
        # Note: params are pre-normalized by the agent loop
        rel_path = params.get("path", "")

        resolved = validate_path(rel_path, workspace_root)
        if resolved is None:
            return ToolResult(
                success=False,
                error=f"Path escapes workspace boundary: {rel_path}",
            )

        if not resolved.exists():
            return ToolResult(success=False, error=f"File not found: {rel_path}")

        if resolved.is_dir():
            return ToolResult(
                success=False,
                error=f"Cannot delete directory with file_delete: {rel_path}",
            )

        try:
            # Read content before deletion so we can show it in the UI
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
