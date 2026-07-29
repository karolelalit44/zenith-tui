"""File change tracker — tracks which files changed during a session."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any


class FileTracker:
    """Tracks file operations within a session for summary and undo awareness."""

    def __init__(self, workspace_root: str) -> None:
        self.root = Path(workspace_root)
        self._changes: dict[str, dict[str, Any]] = {}

    def track(self, file_path: str, operation: str, content: str = "") -> None:
        """Record a file operation."""
        self._changes[file_path] = {
            "operation": operation,
            "content": content[:10000],  # cap stored content
            "timestamp": time.time(),
        }

    def get_changes(self) -> dict[str, dict[str, Any]]:
        """Get all recorded changes."""
        return self._changes.copy()

    def get_changed_files(self) -> list[str]:
        """Get list of changed file paths."""
        return list(self._changes.keys())

    def get_summary(self) -> str:
        """Get human-readable summary of changes."""
        if not self._changes:
            return "No files changed."

        ops = {}
        for info in self._changes.values():
            op = info["operation"]
            ops[op] = ops.get(op, 0) + 1

        parts = [f"{count} {op}" for op, count in ops.items()]
        return f"Changed {len(self._changes)} files: {', '.join(parts)}"

    def has_changes(self) -> bool:
        """Check if any changes have been recorded."""
        return len(self._changes) > 0

    def clear(self) -> None:
        """Clear all recorded changes."""
        self._changes.clear()

    def get_files_by_operation(self, operation: str) -> list[str]:
        """Get files filtered by operation type."""
        return [
            path for path, info in self._changes.items()
            if info["operation"] == operation
        ]
