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

_ACTION_ENUM = ["write", "list", "remove"]
_STATUS_ENUM = ["pending", "in_progress", "completed", "blocked", "cancelled"]
_PRIORITY_ENUM = ["low", "medium", "high"]


def _todo_item_dict(entry: TodoEntry) -> dict:
    """Shape a TodoEntry into the frontend ``TodoItem`` contract."""
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
    """Map internal status to the frontend ``TodoStatus`` vocabulary.

    Frontend: ``todo | in_progress | blocked | done | cancelled``.
    """
    return {
        "pending": "todo",
        "in_progress": "in_progress",
        "completed": "done",
        "blocked": "blocked",
        "cancelled": "cancelled",
    }.get(status, "todo")


class TodoTool(BaseTool):
    name = "todo"
    description = (
        "Write or update a session-scoped task checklist. "
        "Call with ``action=write`` and a ``tasks`` array to replace the "
        "entire board (each item needs at least a ``title``). "
        "Call with ``action=list`` to read the current board. "
        "Call with ``action=remove`` and a ``task_id`` to delete one item."
    )
    capability_id = "task_tracking"
    requires_mode = None
    modes = (PLAN_MODE, BUILD_MODE)
    read_only = False
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_WRITE
    domains = (TOOL_DOMAIN_TASK,)
    search_terms = ("todo", "task", "track", "plan list", "progress")

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: write (set entire board), list, remove",
                    "enum": list(_ACTION_ENUM),
                },
                "task_id": {
                    "type": "string",
                    "description": "Task ID (t1, t2, ...) — required for remove",
                },
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Existing task id (omit to add new)",
                            },
                            "title": {"type": "string", "description": "Task description"},
                            "status": {
                                "type": "string",
                                "enum": list(_STATUS_ENUM),
                                "description": "Task status",
                                "default": "pending",
                            },
                            "priority": {
                                "type": "string",
                                "enum": list(_PRIORITY_ENUM),
                                "description": "Task priority",
                                "default": "medium",
                            },
                        },
                        "required": ["title"],
                    },
                    "description": "Full task list for write action",
                },
            },
            "required": ["action"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        session_id = current_tool_session_id.get() or ""
        action = params.get("action", "")
        if not action:
            return ToolResult(success=False, error="No action provided")

        state = get_todo_state(session_id)

        if action == "write":
            return self._handle_write(state, params)
        elif action == "list":
            return self._handle_list(state)
        elif action == "remove":
            return self._handle_remove(state, params)
        else:
            return ToolResult(
                success=False,
                error=f"Unknown action: {action}. Use one of {', '.join(_ACTION_ENUM)}.",
            )

    def _handle_write(self, state: Any, params: dict[str, Any]) -> ToolResult:
        tasks = params.get("tasks")
        if not isinstance(tasks, list):
            return ToolResult(success=False, error="write requires a tasks array")

        state.reset()
        for item in tasks:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            existing_id = str(item.get("id") or "")
            status = str(item.get("status") or "pending")
            priority = str(item.get("priority") or "medium")
            state.add(
                title,
                priority=priority,
                status=status,
                existing_id=existing_id if existing_id else None,
            )

        board = [_todo_item_dict(e) for e in state.list()]
        message = _format_board(board)
        return ToolResult(
            success=True,
            output=message,
            metadata={"board": board, "action": "write", "count": len(board)},
        )

    def _handle_list(self, state: Any) -> ToolResult:
        entries = state.list()
        if not entries:
            return ToolResult(
                success=True,
                output="No tasks tracked.",
                metadata={"board": [], "action": "list", "count": 0},
            )
        board = [_todo_item_dict(e) for e in entries]
        return ToolResult(
            success=True,
            output=_format_board(board),
            metadata={"board": board, "action": "list", "count": len(board)},
        )

    def _handle_remove(self, state: Any, params: dict[str, Any]) -> ToolResult:
        task_id = str(params.get("task_id") or "")
        if not task_id:
            return ToolResult(success=False, error="No task_id provided")
        if not state.remove(task_id):
            return ToolResult(success=False, error=f"Task {task_id} not found")
        board = [_todo_item_dict(e) for e in state.list()]
        return ToolResult(
            success=True,
            output=f"Task {task_id} removed.",
            metadata={"board": board, "action": "remove", "count": len(board)},
        )


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
