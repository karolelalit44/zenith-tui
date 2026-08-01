"""File write tool — create new files."""

from __future__ import annotations

import re
from typing import Any

from .base import BaseTool, ToolResult
from .path_validator import validate_path

# Patterns indicating placeholder content instead of real content
_PLACEHOLDER_RE = re.compile(
    r"\[[\w\s]*(?:CONTENT|FILE|CODE|PASTE|INSERT|TODO|DESIRED|UPDATED|REPLACE|YOUR)[\w\s]*\]"
    r"|\bYOUR_[\w_]+_HERE\b"
    r"|\b(?:PLACEHOLDER|TODO|FIXME|XXX|TBD)\b"
    r"|\[HTML\]"
    r"|\[ACTUAL_"
    r"|\[Current "
    r"|\[UPDATED_",
    re.IGNORECASE,
)


class FileWriteTool(BaseTool):
    name = "file_write"
    description = "Create a new file with given content"
    requires_mode = "build"

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path for the new file",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Overwrite if file exists (default: false)",
                    "default": False,
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        # Note: params are pre-normalized by the agent loop
        rel_path = params.get("path") or ""
        if not rel_path:
            return ToolResult(success=False, error="Missing file path parameter")

        resolved = validate_path(rel_path, workspace_root)
        if resolved is None:
            return ToolResult(
                success=False,
                error=f"Path escapes workspace boundary: {rel_path}. Use relative paths within the project.",
            )

        content = params.get("content", "")
        overwrite = params.get("overwrite", False)

        # Reject placeholder content
        if content and _PLACEHOLDER_RE.search(content):
            m = _PLACEHOLDER_RE.search(content)
            return ToolResult(
                success=False,
                error=f"Content contains placeholder ({m.group(0)}). Write the actual content, not a placeholder.",
            )

        if resolved.exists() and not overwrite:
            return ToolResult(
                success=False,
                error=f"File already exists: {rel_path}. Use overwrite: true to replace it.",
            )

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"Created {rel_path}",
                metadata={"path": str(resolved)},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
