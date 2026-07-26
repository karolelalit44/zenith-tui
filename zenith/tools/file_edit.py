"""File edit tool — search-replace blocks with fuzzy fallback.

When exact match fails, uses fuzzy matching to find the closest content.
This handles LLMs that slightly modify whitespace or formatting.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .base import BaseTool, ToolResult
from .path_validator import validate_path

# Minimum similarity ratio (0-1) for fuzzy match to be considered valid
FUZZY_THRESHOLD = 0.85


def _fuzzy_find(content: str, old: str) -> tuple[str, float] | None:
    """Find the best fuzzy match of `old` within `content`.

    Returns (matched_text, similarity_ratio) or None if no good match found.
    Uses a sliding window approach for multi-line content.
    """
    if not old or not content:
        return None

    old_lines = old.splitlines()
    content_lines = content.splitlines()

    if not old_lines:
        return None

    best_ratio = 0.0
    best_match = None

    old_len = len(old_lines)
    content_len = len(content_lines)

    # For short patterns (≤5 lines), use sliding window
    if old_len <= 5:
        for start in range(content_len - old_len + 1):
            window = "\n".join(content_lines[start:start + old_len])
            ratio = SequenceMatcher(None, old, window).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = window
    else:
        # For longer patterns, check line-by-line alignment
        for start in range(content_len - old_len + 1):
            window = "\n".join(content_lines[start:start + old_len])
            ratio = SequenceMatcher(None, old, window).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = window

    if best_ratio >= FUZZY_THRESHOLD and best_match is not None:
        return best_match, best_ratio

    return None


class FileEditTool(BaseTool):
    name = "file_edit"
    description = "Edit an existing file using search-replace with fuzzy fallback"
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

            # Try exact match first
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
                    metadata={"path": str(resolved), "changes": 1, "match": "exact"},
                )

            # Fuzzy fallback: find closest match
            fuzzy_result = _fuzzy_find(content, old)
            if fuzzy_result is not None:
                fuzzy_match, ratio = fuzzy_result
                new_content = content.replace(fuzzy_match, new, 1)
                resolved.write_text(new_content, encoding="utf-8")
                return ToolResult(
                    success=True,
                    output=f"Edited {rel_path} (fuzzy match, {ratio:.0%} similarity)",
                    metadata={"path": str(resolved), "changes": 1, "match": "fuzzy", "similarity": round(ratio, 3)},
                )

            # No match found
            preview = old[:80] + ("..." if len(old) > 80 else "")
            return ToolResult(
                success=False,
                error=f"Content not found in file (tried exact + fuzzy matching): {preview}",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
