from __future__ import annotations

import time
from pathlib import Path
from typing import Any


class FileTracker:
    def __init__(self, workspace_root: str) -> None:
        self.root = Path(workspace_root)
        self._changes: dict[str, dict[str, Any]] = {}

    def track(self, file_path: str, operation: str, content: str = "") -> None:
        self._changes[file_path] = {
            "operation": operation,
            "content": content[:10000],
            "timestamp": time.time(),
        }

    def get_changes(self) -> dict[str, dict[str, Any]]:
        return self._changes.copy()

    def get_changed_files(self) -> list[str]:
        return list(self._changes.keys())

    def get_summary(self) -> str:
        if not self._changes:
            return "No files changed."
        ops = {}
        for info in self._changes.values():
            op = info["operation"]
            ops[op] = ops.get(op, 0) + 1
        parts = [f"{count} {op}" for op, count in ops.items()]
        return f"Changed {len(self._changes)} files: {', '.join(parts)}"

    def has_changes(self) -> bool:
        return len(self._changes) > 0

    def clear(self) -> None:
        self._changes.clear()

    def get_files_by_operation(self, operation: str) -> list[str]:
        return [path for path, info in self._changes.items() if info["operation"] == operation]
