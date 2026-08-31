"""QA-5: session-scoped, persistent todo system.

Covers the TodoState store (all ops, stable ids, session isolation), the
contextvar plumbing that gives the TodoTool its session id, the ``todo_board``
event emitted on mutation, and plan-mode availability.
"""

from __future__ import annotations

import pytest

from server.agents.todo_state import (
    TodoState,
    get_todo_state,
    remove_todo_state,
    render_todo_markdown,
    reset_todo_states,
)
from server.toolkit.registry import current_tool_session_id


@pytest.fixture(autouse=True)
def _clean_todo_store():
    reset_todo_states()
    yield
    reset_todo_states()


class TestTodoStateOps:
    def test_add_and_stable_ids(self):
        state = TodoState("s1")
        a = state.add("First task")
        b = state.add("Second task", priority="high")
        assert a.id == "t1"
        assert b.id == "t2"
        assert a.status == "pending"
        assert b.priority == "high"
        assert a.order == 0
        assert b.order == 1

    def test_update_title_status_priority(self):
        state = TodoState("s1")
        t = state.add("Task")
        updated = state.update(t.id, title="Renamed", status="in_progress", priority="low")
        assert updated.title == "Renamed"
        assert updated.status == "in_progress"
        assert updated.priority == "low"

    def test_update_unknown_id_returns_none(self):
        state = TodoState("s1")
        assert state.update("t99", status="completed") is None

    def test_complete_via_update(self):
        state = TodoState("s1")
        t = state.add("Task")
        updated = state.update(t.id, status="completed")
        assert updated.status == "completed"

    def test_remove(self):
        state = TodoState("s1")
        t = state.add("Task")
        assert state.remove(t.id) is True
        assert state.get(t.id) is None
        assert state.remove(t.id) is False

    def test_list_sorted_by_order(self):
        state = TodoState("s1")
        state.add("First")
        state.add("Second")
        state.add("Third")
        assert [t.title for t in state.list()] == ["First", "Second", "Third"]

    def test_snapshot_and_hydrate_round_trip(self):
        state = TodoState("s1")
        state.add("A", priority="high", depends_on=["x"], notes="n1")
        state.add("B")
        state.update("t2", status="completed")
        snap = state.snapshot()
        assert len(snap) == 2

        restored = TodoState("s1")
        restored.hydrate(snap)
        assert restored.list()[0].title == "A"
        assert restored.list()[0].priority == "high"
        assert restored.list()[0].depends_on == ["x"]
        assert restored.list()[1].status == "completed"
        added = restored.add("C")
        assert added.id == "t3"

    def test_invalid_status_kept_unchanged(self):
        state = TodoState("s1")
        t = state.add("Task")
        state.update(t.id, status="bogus")
        assert state.get(t.id).status == "pending"

    def test_reset_clears_board(self):
        state = TodoState("s1")
        state.add("A")
        state.add("B")
        assert len(state.list()) == 2
        state.reset()
        assert len(state.list()) == 0


class TestSessionIsolation:
    def test_two_sessions_isolated(self):
        a = get_todo_state("sess-a")
        b = get_todo_state("sess-b")
        a.add("A task")
        b.add("B task")
        assert [t.title for t in a.list()] == ["A task"]
        assert [t.title for t in b.list()] == ["B task"]

    def test_same_session_shared(self):
        get_todo_state("shared").add("One")
        assert len(get_todo_state("shared").list()) == 1

    def test_remove_session_state(self):
        get_todo_state("s1").add("Task")
        remove_todo_state("s1")
        assert get_todo_state("s1").list() == []


class TestContextVarPlumbing:
    async def test_current_tool_session_id_contextvar(self):
        """Registry sets the session id before tool.execute; TodoTool reads it."""
        from server.toolkit.tools.todo import TodoTool
        from server.toolkit.registry import ToolRegistry

        registry = ToolRegistry()
        registry.register(TodoTool())

        captured = {}

        class WrappingTool(TodoTool):
            async def execute(self, params, workspace_root):
                captured["session_id"] = current_tool_session_id.get()
                return await super().execute(params, workspace_root)

        registry2 = ToolRegistry()
        registry2.register(WrappingTool())
        result = await registry2.execute(
            "todo", {"action": "write", "tasks": [{"title": "T"}]}, "/tmp", session_id="ses-x"
        )
        assert result.success
        assert captured["session_id"] == "ses-x"
        assert result.metadata["board"]
        assert [t["id"] for t in get_todo_state("ses-x").snapshot()] == ["t1"]


class TestTodoBoardEvent:
    async def test_post_execution_hooks_emits_todo_board(self):
        from server.domain.events import EventKind
        from server.toolkit.executor import post_execution_hooks
        from server.toolkit.tools.todo import TodoTool
        from server.toolkit.registry import ToolRegistry

        registry = ToolRegistry()
        registry.register(TodoTool())
        result = await registry.execute(
            "todo",
            {"action": "write", "tasks": [{"title": "A board item"}]},
            "/tmp",
            session_id="s-b",
        )
        assert result.success
        events = await post_execution_hooks("todo", {}, result, "/tmp", "s-b")
        todo_events = [e for e in events if e.kind == EventKind.TODO_BOARD]
        assert len(todo_events) == 1
        ev = todo_events[0]
        assert ev.data["action"] == "write"
        board = ev.data["board"]
        assert isinstance(board, list) and board
        assert board[0]["id"] == "t1"
        assert board[0]["title"] == "A board item"
        assert board[0]["status"] == "todo"
        assert board[0]["priority"] == "medium"
        assert "subtasks" in board[0]
        assert "updatedAt" in board[0]

    async def test_non_todo_tool_no_event(self):
        from server.domain.events import EventKind
        from server.toolkit.executor import post_execution_hooks
        from server.toolkit.base import ToolResult

        events = await post_execution_hooks(
            "file_read", {}, ToolResult(success=True, output="x"), "/tmp", "s"
        )
        assert not [e for e in events if e.kind == EventKind.TODO_BOARD]

    async def test_todo_events_flow_through_registry_scope(self):
        from server.toolkit.executor import execute_tool
        from server.toolkit.tools.todo import TodoTool
        from server.toolkit.registry import ToolRegistry

        registry = ToolRegistry()
        registry.register(TodoTool())
        result, _ = await execute_tool(
            registry, "todo", {"action": "write", "tasks": [{"title": "X"}]}, "/tmp", "build"
        )
        assert result.success
        assert result.metadata["board"]


class TestRenderTodoMarkdown:
    """QA-5.8: the todo.md artifact mirrors the structured todo snapshot."""

    def test_markers_per_status(self):
        state = TodoState("s1")
        state.add("Pending task")
        state.add("Working task")
        state.update("t2", status="in_progress")
        state.add("Completed task")
        state.update("t3", status="completed")
        text = render_todo_markdown(state.snapshot())
        assert "- [ ] Pending task" in text
        assert "- [~] Working task" in text
        assert "- [x] Completed task" in text

    def test_priority_and_notes_suffix(self):
        state = TodoState("s1")
        state.add("High task", priority="high", notes="needs schema change")
        text = render_todo_markdown(state.snapshot())
        assert "- [ ] High task (priority: high) — needs schema change" in text

    def test_medium_priority_omitted(self):
        state = TodoState("s1")
        state.add("Plain task")
        text = render_todo_markdown(state.snapshot())
        assert "- [ ] Plain task\n" in text
        assert "priority" not in text

    def test_order_preserved(self):
        state = TodoState("s1")
        state.add("First")
        state.add("Second")
        state.add("Third")
        text = render_todo_markdown(state.snapshot())
        lines = [ln for ln in text.splitlines() if ln.startswith("- ")]
        assert lines == [
            "- [ ] First",
            "- [ ] Second",
            "- [ ] Third",
        ]

    def test_empty_board_renders_header_only(self):
        assert render_todo_markdown([]) == "# Todos\n\n"

    def test_in_progress_and_blocked_and_cancelled_markers(self):
        state = TodoState("s1")
        state.add("A")
        state.update("t1", status="in_progress")
        state.add("B")
        state.update("t2", status="blocked")
        state.add("C")
        state.update("t3", status="cancelled")
        text = render_todo_markdown(state.snapshot())
        assert "- [~] A" in text
        assert "- [!] B" in text
        assert "- [-] C" in text


class TestPlanModeAvailability:
    def test_todo_available_in_plan_and_build_but_not_read_only(self):
        from server.toolkit.tools.todo import TodoTool

        tool = TodoTool()
        modes = set(tool.modes)
        assert "plan" in modes
        assert "build" in modes
        assert "read_only" not in modes
