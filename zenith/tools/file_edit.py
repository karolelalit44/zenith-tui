"""File edit tool — search-replace blocks in existing files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseTool, ToolResult
from .path_validator import validate_path


class FileEditTool(BaseTool):
    name = "file_edit"
    description = "Edit an existing file using search-replace"
    requires_mode = "build"

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_content": {
                    "type": "string",
                    "description": "The exact content to find and replace",
                },
                "new_content": {
                    "type": "string",
                    "description": "The replacement content",
                },
            },
            "required": ["path", "old_content", "new_content"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        # Note: params are pre-normalized by the agent loop
        rel_path = params.get("path") or ""

        resolved = validate_path(rel_path, workspace_root)
        if resolved is None:
            return ToolResult(
                success=False,
                error=f"Path escapes workspace boundary: {rel_path}",
            )

        old = params.get("old_content", "")
        new = params.get("new_content", "")

        if not resolved.exists():
            return ToolResult(success=False, error=f"File not found: {rel_path}")

        if not old:
            return ToolResult(success=False, error="old_content cannot be empty")

        try:
            content = resolved.read_text(encoding="utf-8")

            if old not in content:
                preview = old[:80] + ("..." if len(old) > 80 else "")
                return ToolResult(
                    success=False,
                    error=f"Content not found in file: {preview}",
                )

            count = content.count(old)
            if count > 1:
                return ToolResult(
                    success=False,
                    error=f"Ambiguous: found {count} matches. Provide more surrounding context.",
                )

            new_content = content.replace(old, new, 1)
            resolved.write_text(new_content, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"Edited {rel_path}",
                metadata={"path": str(resolved), "changes": 1},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
