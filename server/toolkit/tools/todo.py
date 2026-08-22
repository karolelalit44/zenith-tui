from __future__ import annotations

import logging
import time
from typing import Any

from server.agents.todo_state import TodoEntry, get_todo_state
from server.config.constants import (
    BUILD_MODE,
    CONCURRENCY_GROUP_READONLY,
    PERMISSION_WRITE,
    PLAN_MODE,
    TOOL_DOMAIN_TASK,
)
from server.toolkit.registry import current_tool_session_id

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

_ACTION_ENUM = ["add", "update", "complete", "fail", "reopen", "reorder", "remove", "list"]
_STATUS_ENUM = ["pending", "in_progress", "completed", "blocked", "failed", "cancelled"]
_PRIORITY_ENUM = ["low", "medium", "high"]


def _todo_item_dict(entry: TodoEntry) -> dict:
    """Shape a TodoEntry into the frontend `TodoItem` contract (todo_board board)."""
    return {
        "id": entry.id,
        "title": entry.title,
        "status": _map_status(entry.status),
        "priority": entry.priority,
        "order": entry.order,
        "depends_on": list(entry.depends_on),
        "notes": entry.notes,
        "createdAt": 0,
        "updatedAt": int(time.time() * 1000),
        "subtasks": [],
    }


def _map_status(status: str) -> str:
    """Map internal status to the frontend TodoStatus vocabulary.

    Frontend: ``todo | in_progress | blocked | done | cancelled``. ``pending``
    becomes ``todo``; ``completed``/``failed`` map to ``done``/``blocked`` so the
    board renderer's status→tone mapping keeps working.
    """
    return {
        "pending": "todo",
        "in_progress": "in_progress",
        "completed": "done",
        "blocked": "blocked",
        "failed": "blocked",
        "cancelled": "cancelled",
    }.get(status, "todo")


class TodoTool(BaseTool):
    name = "todo"
    description = "Track a session-scoped task list"
    capability_id = "task_tracking"
    # Plan mode needs task tracking too (QA-5.6), but read_only must stay
    # non-mutating: todo mutates persisted task state, so it is gated to
    # plan + build only.
    requires_mode = None
    modes = (PLAN_MODE, BUILD_MODE)
    read_only = False
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_WRITE
    domains = (TOOL_DOMAIN_TASK,)
    search_terms = (
        "todo",
        "task",
        "track",
        "plan list",
        "progress",
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: add, update, complete, fail, reopen, reorder, remove, list",
                    "enum": list(_ACTION_ENUM),
                },
                "task_id": {"type": "string", "description": "Task ID (t1, t2, ...)"},
                "description": {"type": "string", "description": "Task description / title"},
                "status": {
                    "type": "string",
                    "description": "Status: pending, in_progress, completed, blocked, failed, cancelled",
                    "enum": list(_STATUS_ENUM),
                },
                "priority": {
                    "type": "string",
                    "description": "Priority: low, medium, high",
                    "enum": list(_PRIORITY_ENUM),
                    "default": "medium",
                },
                "order": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered list of task ids for reorder",
                },
                "depends_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task ids this task depends on",
                },
                "notes": {"type": "string", "description": "Optional notes"},
            },
            "required": ["action"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        # Session id comes from server-side state (set by Registry.execute via
        # the contextvar), never from model-supplied params.
        session_id = current_tool_session_id.get() or ""
        action = params.get("action", "")
        if not action:
            return ToolResult(success=False, error="No action provided")
        state = get_todo_state(session_id)
        board: list[dict] = []
        action_name = action
        message = ""

        if action == "add":
            description = str(params.get("description") or "").strip()
            if not description:
                return ToolResult(success=False, error="No task description provided")
            entry = state.add(
                description,
                priority=str(params.get("priority") or "medium"),
                depends_on=[str(x) for x in (params.get("depends_on") or [])],
                notes=str(params.get("notes") or ""),
            )
            board = [_todo_item_dict(e) for e in state.list()]
            message = f"Task {entry.id} added: {entry.title} (priority: {entry.priority})"
        elif action == "update":
            task_id = str(params.get("task_id") or "")
            if not task_id:
                return ToolResult(success=False, error="No task_id provided")
            entry = state.update(
                task_id,
                title=params.get("description"),
                status=params.get("status"),
                priority=params.get("priority"),
                notes=params.get("notes"),
            )
            if entry is None:
                return ToolResult(success=False, error=f"Task {task_id} not found")
            board = [_todo_item_dict(e) for e in state.list()]
            message = (
                f"Task {entry.id} updated: {entry.title} "
                f"(status: {entry.status}, priority: {entry.priority})"
            )
        elif action == "complete":
            task_id = str(params.get("task_id") or "")
            entry = state.complete(task_id) if task_id else None
            if entry is None:
                return ToolResult(success=False, error=f"Task {task_id} not found")
            board = [_todo_item_dict(e) for e in state.list()]
            message = f"Task {entry.id} completed: {entry.title}"
        elif action == "fail":
            task_id = str(params.get("task_id") or "")
            entry = state.fail(task_id) if task_id else None
            if entry is None:
                return ToolResult(success=False, error=f"Task {task_id} not found")
            board = [_todo_item_dict(e) for e in state.list()]
            message = f"Task {entry.id} failed: {entry.title}"
        elif action == "reopen":
            task_id = str(params.get("task_id") or "")
            entry = state.reopen(task_id) if task_id else None
            if entry is None:
                return ToolResult(success=False, error=f"Task {task_id} not found")
            board = [_todo_item_dict(e) for e in state.list()]
            message = f"Task {entry.id} reopened: {entry.title}"
        elif action == "reorder":
            ordered = [str(x) for x in (params.get("order") or [])]
            if not ordered:
                return ToolResult(success=False, error="No order list provided")
            state.reorder(ordered)
            board = [_todo_item_dict(e) for e in state.list()]
            message = "Tasks reordered."
        elif action == "remove":
            task_id = str(params.get("task_id") or "")
            if not state.remove(task_id):
                return ToolResult(success=False, error=f"Task {task_id} not found")
            board = [_todo_item_dict(e) for e in state.list()]
            message = f"Task {task_id} removed."
        elif action == "list":
            entries = state.list()
            if not entries:
                return ToolResult(
                    success=True,
                    output="No tasks tracked.",
                    metadata={"board": [], "action": "list", "count": 0},
                )
            board = [_todo_item_dict(e) for e in entries]
            message = _format_board(board)
        else:
            return ToolResult(
                success=False,
                error=f"Unknown action: {action}. Use one of {', '.join(_ACTION_ENUM)}.",
            )

        metadata = {"board": board, "action": action_name, "count": len(board)}
        return ToolResult(success=True, output=message, metadata=metadata)


def _format_board(board: list[dict]) -> str:
    if not board:
        return "No tasks tracked."
    done = sum(1 for t in board if t["status"] == "done")
    lines = [f"Tasks: {done}/{len(board)} done"]
    for t in board:
        status = {
            "todo": "pending",
            "in_progress": "in_progress",
            "done": "completed",
            "blocked": "blocked",
            "cancelled": "cancelled",
        }.get(t["status"], t["status"])
        mark = {
            "completed": "[x]",
            "in_progress": "[~]",
            "pending": "[ ]",
            "blocked": "[!]",
            "cancelled": "[-]",
        }.get(status, "[ ]")
        lines.append(f"  {mark} [{t['id']}] ({t['priority']}) {t['title']}")
    return "\n".join(lines)
