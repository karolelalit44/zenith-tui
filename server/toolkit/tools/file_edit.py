from __future__ import annotations

from difflib import unified_diff
from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_WORKSPACE_MUTATION,
    PERMISSION_WRITE,
    TOOL_DOMAIN_EDIT,
)
from server.workspace.ignore import blocked_as_missing, get_matcher

from ..base import BaseTool, ToolResult
from ..path_validator import validate_path
from .file_mutation_queue import FILE_MUTATION_QUEUE


def _unified_patch(rel_path: str, before: str, after: str) -> str:
    return "".join(
        unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
        )
    )


class FileEditTool(BaseTool):
    name = "file_edit"
    description = "Edit file via search-replace"
    requires_mode = None
    capability_id = "file_edit"
    read_only = False
    concurrency_group = CONCURRENCY_GROUP_WORKSPACE_MUTATION
    permission_scope = PERMISSION_WRITE
    domains = (TOOL_DOMAIN_EDIT,)
    search_terms = (
        "edit",
        "modify",
        "update",
        "replace",
        "patch",
        "change",
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "old_content": {"type": "string", "description": "Text to replace"},
                "new_content": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_content", "new_content"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        rel_path = params.get("path") or ""
        resolved = validate_path(rel_path, workspace_root)
        if resolved is None:
            return ToolResult(success=False, error=f"Path escapes workspace boundary: {rel_path}")
        if blocked_as_missing(get_matcher(workspace_root), rel_path):
            return ToolResult(success=False, error=f"File not found: {rel_path}")
        old = params.get("old_content", "")
        new = params.get("new_content", "")
        if not resolved.exists():
            return ToolResult(success=False, error=f"File not found: {rel_path}")
        if not old:
            return ToolResult(success=False, error="old_content cannot be empty")
        try:
            # Read-modify-write is atomic under the per-workspace mutation lock
            # so concurrent edits cannot both read stale content (opencode's
            # file-mutation Semaphore). Validation stays outside the critical
            # section; only the filesystem read/scan-write is serialized.
            async with FILE_MUTATION_QUEUE.mutation(workspace_root):
                content = resolved.read_text(encoding="utf-8")
                if old in content:
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
                        metadata={
                            "path": str(resolved),
                            "changes": 1,
                            "match": "exact",
                            "diff": _unified_patch(rel_path, content, new_content),
                        },
                    )
                preview = old[:80] + ("..." if len(old) > 80 else "")
                return ToolResult(
                    success=False,
                    error=f"Content not found in file (exact match only): {preview}",
                )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
