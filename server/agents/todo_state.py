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

# What counts as "still open work". Defined once here because the nudge path and
# the completion path previously carried their own tuples and disagreed about
# `blocked`: the nudge ignored it while completion counted it, so a fully blocked
# board got neither a nudge nor a clean completion.
#
# `blocked` IS active — work that cannot proceed is unfinished work. Callers that
# want only actionable items pass include_blocked=False.
ACTIVE_TODO_STATUSES: frozenset[str] = frozenset({"pending", "in_progress"})
ACTIONABLE_TODO_STATUSES: frozenset[str] = ACTIVE_TODO_STATUSES | {"blocked"}

_TODO_STATUS_MARKERS = {
    "pending": "[ ]",
    "in_progress": "[~]",
    "completed": "[x]",
    "blocked": "[!]",
    "cancelled": "[-]",
}


def normalize_status(status: str | None) -> str:
    """Normalize user- or model-provided status into canonical TodoStatus."""
    s = str(status or "").strip().lower().replace("-", "_").replace(" ", "_")
    if s in ("todo", "pending", "open", "queued", "not_started"):
        return "pending"
    if s in ("in_progress", "inprogress", "running", "active", "working"):
        return "in_progress"
    if s in ("completed", "done", "success", "finished", "resolved", "closed"):
        return "completed"
    if s in ("blocked", "waiting", "paused", "stalled"):
        return "blocked"
    if s in ("cancelled", "canceled", "aborted", "failed", "rejected"):
        return "cancelled"
    return "pending"


def render_todo_markdown(entries: list[dict] | list[TodoEntry]) -> str:
    """Render structured todos into the canonical ``todo.md`` artifact."""
    lines = ["# Todos", ""]
    for entry in entries:
        data = entry.to_dict() if isinstance(entry, TodoEntry) else entry
        status = normalize_status(str(data.get("status") or "pending"))
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
    def from_dict(data: dict[str, Any]) -> TodoEntry:
        return TodoEntry(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            status=normalize_status(str(data.get("status") or "pending")),
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
        norm_status = normalize_status(status)
        if existing_id and existing_id in self._entries:
            entry = self._entries[existing_id]
            entry.title = title
            entry.status = norm_status
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
            status=norm_status,
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
            entry.status = normalize_status(status)
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

    def active(self, *, include_blocked: bool = True) -> list[TodoEntry]:
        """Entries still representing open work, in board order.

        One definition of "active" for every caller. ``include_blocked`` is True
        by default because a blocked task is unfinished work: excluding it from
        completion reporting is what previously let a fully blocked board report
        as finished.
        """
        statuses = ACTIONABLE_TODO_STATUSES if include_blocked else ACTIVE_TODO_STATUSES
        return [e for e in self.list() if e.status in statuses]

    def has_active(self, *, include_blocked: bool = True) -> bool:
        return bool(self.active(include_blocked=include_blocked))

    def is_resolved(self) -> bool:
        """True when nothing on the board is outstanding."""
        return not self.active()

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


def reset_todo_state(session_id: str) -> None:
    """Clear the session board at turn entry.

    The board's lifetime is the request's, not the session's. Without this, a
    finished checklist from the previous request is still on the board when the
    next one starts: the nudge logic reads it as outstanding work, the client
    re-pins it above the composer, and both surfaces claim the new request is
    carrying someone else's work.

    A session that genuinely spans requests re-establishes its checklist with an
    explicit ``todo`` call. Carry-over must be asked for, never inferred.
    """
    if not session_id:
        return
    with _LOCK:
        state = _STORE.get(session_id)
        if state is not None:
            state.reset()




_SESSIONLESS_TODO = TodoState("__sessionless__")
