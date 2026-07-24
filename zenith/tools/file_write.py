"""File write tool — create new files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseTool, ToolResult
from .param_normalizer import normalize_file_params


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
            },
            "required": ["path", "content"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        params = normalize_file_params(params)
        rel_path = params.get("path") or ""
        if not rel_path:
            return ToolResult(success=False, error="Missing file path parameter")

        path = Path(workspace_root) / rel_path
        content = params.get("content", "")
        overwrite = params.get("overwrite", False)

        if path.exists() and not overwrite:
            return ToolResult(
                success=False,
                error=f"File already exists: {path}. Use file_edit to modify or set overwrite: true.",
            )

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"Created {path}",
                metadata={"path": str(path)},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
