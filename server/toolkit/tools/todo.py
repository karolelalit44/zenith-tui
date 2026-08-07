from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    PERMISSION_WRITE,
    TOOL_DOMAIN_TASK,
)

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class Task:
    id: str
    description: str
    status: str = "pending"
    priority: str = "medium"


class TaskTracker:
    def __init__(self) -> None:
        self._tasks: list[Task] = []
        self._next_id: int = 1

    def add(self, description: str, priority: str = "medium") -> Task:
        task = Task(id=str(self._next_id), description=description, priority=priority)
        self._tasks.append(task)
        self._next_id += 1
        return task

    def update(
        self, task_id: str, status: str | None = None, description: str | None = None
    ) -> Task | None:
        for task in self._tasks:
            if task.id == task_id:
                if status:
                    task.status = status
                if description:
                    task.description = description
                return task
        return None

    def get_all(self) -> list[Task]:
        return self._tasks.copy()

    def format_summary(self) -> str:
        if not self._tasks:
            return "No tasks tracked."
        pending = [t for t in self._tasks if t.status == "pending"]
        in_progress = [t for t in self._tasks if t.status == "in_progress"]
        completed = [t for t in self._tasks if t.status == "completed"]
        cancelled = [t for t in self._tasks if t.status == "cancelled"]
        lines: list[str] = []
        lines.append(f"Tasks: {len(completed)}/{len(self._tasks)} completed")
        if in_progress:
            lines.append("\nIn Progress:")
            for t in in_progress:
                lines.append(f"  [{t.id}] ({t.priority}) {t.description}")
        if pending:
            lines.append("\nPending:")
            for t in pending:
                lines.append(f"  [{t.id}] ({t.priority}) {t.description}")
        if completed:
            lines.append("\nCompleted:")
            for t in completed:
                lines.append(f"  [{t.id}] {t.description}")
        if cancelled:
            lines.append("\nCancelled:")
            for t in cancelled:
                lines.append(f"  [{t.id}] {t.description}")
        return "\n".join(lines)


_task_tracker: TaskTracker | None = None


def get_task_tracker() -> TaskTracker:
    global _task_tracker
    if _task_tracker is None:
        _task_tracker = TaskTracker()
    return _task_tracker


class TodoTool(BaseTool):
    name = "todo"
    description = "Track task list"
    capability_id = "task_tracking"
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
                    "description": "Action: add, update, list, summary",
                    "enum": ["add", "update", "list", "summary"],
                },
                "task_id": {"type": "string", "description": "Task ID"},
                "description": {"type": "string", "description": "Task description"},
                "status": {
                    "type": "string",
                    "description": "Status: pending, in_progress, completed, cancelled",
                    "enum": ["pending", "in_progress", "completed", "cancelled"],
                },
                "priority": {
                    "type": "string",
                    "description": "Priority: low, medium, high",
                    "enum": ["low", "medium", "high"],
                    "default": "medium",
                },
            },
            "required": ["action"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        action = params.get("action", "")
        if not action:
            return ToolResult(success=False, error="No action provided")
        tracker = get_task_tracker()
        if action == "add":
            description = params.get("description", "")
            if not description:
                return ToolResult(success=False, error="No task description provided")
            priority = params.get("priority", "medium")
            task = tracker.add(description, priority)
            return ToolResult(
                success=True,
                output=f"Task {task.id} added: {task.description} (priority: {task.priority})",
                metadata={"task_id": task.id, "action": "add"},
            )
        elif action == "update":
            task_id = params.get("task_id", "")
            if not task_id:
                return ToolResult(success=False, error="No task_id provided")
            status = params.get("status")
            description = params.get("description")
            task = tracker.update(task_id, status=status, description=description)
            if task is None:
                return ToolResult(success=False, error=f"Task {task_id} not found")
            return ToolResult(
                success=True,
                output=f"Task {task.id} updated: {task.description} (status: {task.status})",
                metadata={"task_id": task.id, "action": "update"},
            )
        elif action == "list":
            tasks = tracker.get_all()
            if not tasks:
                return ToolResult(success=True, output="No tasks tracked.")
            output = tracker.format_summary()
            return ToolResult(success=True, output=output, metadata={"count": len(tasks)})
        elif action == "summary":
            output = tracker.format_summary()
            return ToolResult(success=True, output=output)
        else:
            return ToolResult(
                success=False,
                error=f"Unknown action: {action}. Use 'add', 'update', 'list', or 'summary'.",
            )
