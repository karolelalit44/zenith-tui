"""Multi-edit tool — apply multiple find/replace edits to a single file atomically.

Unlike file_edit which applies one edit at a time, multi_edit applies all
edits in sequence, verifying each step.  If any edit fails, the entire
operation is rolled back (the file is restored to its original state).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class MultiEditTool(BaseTool):
    name = "multi_edit"
    description = "Apply multiple find/replace edits to a single file atomically. All edits succeed or none do."
    requires_mode = "build"

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Absolute path to the file to edit",
                },
                "edits": {
                    "type": "array",
                    "description": "List of edits to apply in order. Each edit is {old_content, new_content}.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_content": {
                                "type": "string",
                                "description": "The exact text to find and replace (must appear exactly once in the file)",
                            },
                            "new_content": {
                                "type": "string",
                                "description": "The text to replace it with",
                            },
                        },
                        "required": ["old_content", "new_content"],
                    },
                },
            },
            "required": ["filepath", "edits"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        filepath = params.get("filepath", "")
        edits = params.get("edits", [])

        if not filepath:
            return ToolResult(success=False, error="No filepath provided")
        if not edits:
            return ToolResult(success=False, error="No edits provided")

        # Resolve path
        path = Path(filepath)
        if not path.is_absolute():
            path = Path(workspace_root) / filepath
        path = path.resolve()

        # Read original content for rollback
        try:
            original_content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ToolResult(success=False, error=f"File not found: {filepath}")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to read {filepath}: {e}")

        # Apply edits sequentially, rolling back on failure
        current_content = original_content
        applied_count = 0

        for i, edit in enumerate(edits):
            old_content = edit.get("old_content", "")
            new_content = edit.get("new_content", "")

            if not old_content:
                return ToolResult(
                    success=False,
                    error=f"Edit {i + 1}: old_content cannot be empty",
                )

            # Count occurrences
            count = current_content.count(old_content)
            if count == 0:
                # Rollback
                path.write_text(original_content, encoding="utf-8")
                return ToolResult(
                    success=False,
                    error=f"Edit {i + 1}: old_content not found in file. All {applied_count} previous edits were rolled back.",
                )
            if count > 1:
                # Rollback
                path.write_text(original_content, encoding="utf-8")
                return ToolResult(
                    success=False,
                    error=f"Edit {i + 1}: old_content appears {count} times (must appear exactly once). All {applied_count} previous edits were rolled back.",
                )

            current_content = current_content.replace(old_content, new_content, 1)
            applied_count += 1

        # All edits succeeded — write the final content
        try:
            path.write_text(current_content, encoding="utf-8")
        except Exception as e:
            # Best-effort rollback
            try:
                path.write_text(original_content, encoding="utf-8")
            except Exception:
                pass
            return ToolResult(success=False, error=f"Failed to write file after {applied_count} edits: {e}")

        return ToolResult(
            success=True,
            output=f"Applied {applied_count} edit(s) to {filepath}",
            metadata={"filepath": str(path), "edits_applied": applied_count},
        )
