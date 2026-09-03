"""Session-scoped todo checklist (simple store, no lifecycle state machine).

Provides a per-session in-memory todo list that the ``TodoTool`` reads and
writes.  The store is keyed by ``session_id`` and lives in-process for the
lifetime of the server.  Each mutation returns a snapshot so callers can
persist it into session metadata or emit a ``todo_board`` event without a
second read.

Design follows opencode's todowrite: a plain checklist the model writes and
reads — no lifecycle phases, no approval gates, no dependency graph.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

_TODO_STATUSES = ("pending", "in_progress", "completed", "blocked", "cancelled")
_PRIORITIES = ("low", "medium", "high")

_TODO_STATUS_MARKERS = {
    "pending": "[ ]",
    "in_progress": "[~]",
    "completed": "[x]",
    "blocked": "[!]",
    "cancelled": "[-]",
}


def render_todo_markdown(entries: list[dict] | list["TodoEntry"]) -> str:
    """Render structured todos into the canonical ``todo.md`` artifact."""
    lines = ["# Todos", ""]
    for entry in entries:
        data = entry.to_dict() if isinstance(entry, TodoEntry) else entry
        status = str(data.get("status") or "pending")
        marker = _TODO_STATUS_MARKERS.get(status, "[ ]")
        title = str(data.get("title") or "untitled")
        suffix = ""
        priority = str(data.get("priority") or "medium")
        if priority != "medium":
            suffix += f" (priority: {priority})"
        notes = str(data.get("notes") or "").strip()
        if notes:
            suffix += f" — {notes}"
        lines.append(f"- {marker} {title}{suffix}")
    return "\n".join(lines) + "\n"


@dataclass
class TodoEntry:
    id: str
    title: str
    status: str = "pending"
    priority: str = "medium"
    order: int = 0
    depends_on: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "order": self.order,
            "depends_on": list(self.depends_on),
            "notes": self.notes,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "TodoEntry":
        return TodoEntry(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            status=str(data.get("status") or "pending"),
            priority=str(data.get("priority") or "medium"),
            order=int(data.get("order") or 0),
            depends_on=[str(x) for x in (data.get("depends_on") or [])],
            notes=str(data.get("notes") or ""),
        )


class TodoState:
    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._entries: dict[str, TodoEntry] = {}
        self._next_id = 1

    def reset(self) -> None:
        """Clear all entries (used by ``write`` action to replace the board)."""
        self._entries.clear()
        self._next_id = 1

    def add(
        self,
        title: str,
        priority: str = "medium",
        status: str = "pending",
        depends_on: list[str] | None = None,
        notes: str = "",
        existing_id: str | None = None,
    ) -> TodoEntry:
        if existing_id and existing_id in self._entries:
            entry = self._entries[existing_id]
            entry.title = title
            entry.status = status if status in _TODO_STATUSES else entry.status
            entry.priority = priority if priority in _PRIORITIES else entry.priority
            if depends_on is not None:
                entry.depends_on = list(depends_on)
            if notes:
                entry.notes = notes
            return entry

        tid = existing_id if existing_id else f"t{self._next_id}"
        if not existing_id:
            self._next_id += 1
        entry = TodoEntry(
            id=tid,
            title=title,
            status=status if status in _TODO_STATUSES else "pending",
            priority=priority if priority in _PRIORITIES else "medium",
            order=len(self._entries),
            depends_on=list(depends_on or []),
            notes=notes,
        )
        self._entries[tid] = entry
        return entry

    def update(
        self,
        task_id: str,
        title: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        notes: str | None = None,
    ) -> TodoEntry | None:
        entry = self._entries.get(task_id)
        if entry is None:
            return None
        if title is not None:
            entry.title = title
        if status is not None:
            entry.status = status if status in _TODO_STATUSES else entry.status
        if priority is not None:
            entry.priority = priority if priority in _PRIORITIES else entry.priority
        if notes is not None:
            entry.notes = notes
        return entry

    def complete(self, task_id: str) -> TodoEntry | None:
        return self.update(task_id, status="completed")

    def remove(self, task_id: str) -> bool:
        if task_id not in self._entries:
            return False
        del self._entries[task_id]
        return True

    def get(self, task_id: str) -> TodoEntry | None:
        return self._entries.get(task_id)

    def list(self) -> list[TodoEntry]:
        return sorted(self._entries.values(), key=lambda e: e.order)

    def snapshot(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.list()]

    def hydrate(self, entries: list[dict[str, Any]]) -> None:
        """Replace in-memory state from a persisted snapshot."""
        self._entries.clear()
        self._next_id = 1
        for data in entries or []:
            entry = TodoEntry.from_dict(data)
            self._entries[entry.id] = entry
            idx = int(entry.id[1:]) if entry.id.startswith("t") else 0
            self._next_id = max(self._next_id, idx + 1)



_STORE: dict[str, TodoState] = {}
_LOCK = threading.Lock()


def get_todo_state(session_id: str) -> TodoState:
    """Return the session-scoped store, creating it if absent."""
    if not session_id:
        return _SESSIONLESS_TODO
    with _LOCK:
        state = _STORE.get(session_id)
        if state is None:
            state = TodoState(session_id)
            _STORE[session_id] = state
        return state




_SESSIONLESS_TODO = TodoState("__sessionless__")
