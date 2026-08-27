from __future__ import annotations

from typing import Any

from server.agents.validation import PLACEHOLDER_RE
from server.config.constants import (
    CONCURRENCY_GROUP_WORKSPACE_MUTATION,
    FILE_ALREADY_EXISTS_ERROR,
    FILE_OVERWRITE_PARAM,
    PERMISSION_WRITE,
    TOOL_DOMAIN_EDIT,
)
from server.workspace.ignore import blocked_as_missing, get_matcher

from ..base import BaseTool, ToolResult
from ..path_validator import validate_path


class FileWriteTool(BaseTool):
    name = "file_write"
    description = (
        "Create or overwrite a file; missing parent directories are created automatically. "
        "In plan mode, only plan.md/todo.md are writable."
    )
    requires_mode = None
    capability_id = "file_write"
    read_only = False
    concurrency_group = CONCURRENCY_GROUP_WORKSPACE_MUTATION
    permission_scope = PERMISSION_WRITE
    domains = (TOOL_DOMAIN_EDIT,)
    search_terms = (
        "create",
        "write",
        "new file",
        "generate file",
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "File path; any missing parent directories are created automatically"
                    ),
                },
                "content": {"type": "string", "description": "File content"},
                FILE_OVERWRITE_PARAM: {
                    "type": "boolean",
                    "description": "Overwrite existing",
                    "default": False,
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        rel_path = params.get("path") or ""
        if not rel_path:
            return ToolResult(success=False, error="Missing file path parameter")
        resolved = validate_path(rel_path, workspace_root)
        if resolved is None:
            return ToolResult(
                success=False,
                error=f"Path escapes workspace boundary: {rel_path}. Use relative paths within the project.",
            )
        if blocked_as_missing(get_matcher(workspace_root), rel_path):
            return ToolResult(success=False, error=f"File not found: {rel_path}")
        content = params.get("content", "")
        overwrite = params.get(FILE_OVERWRITE_PARAM, False)
        if content:
            m = PLACEHOLDER_RE.search(content)
            if m:
                return ToolResult(
                    success=False,
                    error=f"Content contains placeholder ({m.group(0)}). Write the actual content, not a placeholder.",
                )
        if resolved.exists() and (not overwrite):
            return ToolResult(
                success=False,
                error=FILE_ALREADY_EXISTS_ERROR.format(
                    path=rel_path, overwrite_param=FILE_OVERWRITE_PARAM
                ),
            )
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"Created {rel_path} ({len(content)} bytes)",
                metadata={"path": str(resolved), "bytes": len(content)},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
