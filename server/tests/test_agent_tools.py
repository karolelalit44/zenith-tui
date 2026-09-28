import pytest

from server.agents.loop import _format_tool_result
from server.domain.events import EventKind
from server.providers.parser import parse_tool_calls
from server.toolkit.base import ToolResult


class TestResponderSuccess:
    def test_success_carries_elapsed_ms(self):
        from server.providers.responder import success

        evt = success("done", "s1", iterations=3, elapsed_ms=4250)
        assert evt.kind == EventKind.SUCCESS
        assert evt.data["elapsedMs"] == 4250
        assert evt.data["duration"] == 4250

    def test_success_without_elapsed_omits_duration_fields(self):
        from server.providers.responder import success

        evt = success("done", "s1", iterations=1)
        assert "elapsedMs" not in evt.data
        assert "duration" not in evt.data


class TestParseToolCalls:
    def test_parse_single_tool_call(self):
        text = 'Here is my response.\n```tool\n{"tool": "bash", "params": {"command": "ls"}}\n```'
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["tool"] == "bash"
        assert calls[0]["params"]["command"] == "ls"

    def test_parse_multiple_tool_calls(self):
        text = 'Let me check.\n```tool\n{"tool": "glob", "params": {"pattern": "*.py"}}\n```\nAnd also.\n```tool\n{"tool": "grep", "params": {"pattern": "def"}}\n```'
        calls = parse_tool_calls(text)
        assert len(calls) == 2
        assert calls[0]["tool"] == "glob"
        assert calls[1]["tool"] == "grep"

    def test_parse_no_tool_calls(self):
        text = "Just a normal response with no tool calls."
        calls = parse_tool_calls(text)
        assert len(calls) == 0

    def test_parse_invalid_json(self):
        text = "```tool\nnot json\n```"
        calls = parse_tool_calls(text)
        assert len(calls) == 0

    def test_parse_missing_tool_key(self):
        text = '```tool\n{"params": {"command": "ls"}}\n```'
        calls = parse_tool_calls(text)
        assert len(calls) == 0

    def test_parse_mixed_content(self):
        text = 'I will run two commands.\n```tool\n{"tool": "bash", "params": {"command": "echo a"}}\n```\nAnd also this.\n```tool\n{"tool": "bash", "params": {"command": "echo b"}}\n```\nDone!'
        calls = parse_tool_calls(text)
        assert len(calls) == 2


class TestFormatToolResult:
    def test_format_success(self):
        result = ToolResult(success=True, output="file contents here")
        formatted = _format_tool_result("file_read", result)
        assert "SUCCESS" in formatted
        assert "file_read" in formatted
        assert "file contents here" in formatted

    def test_format_failure(self):
        result = ToolResult(success=False, error="File not found")
        formatted = _format_tool_result("file_read", result)
        assert "FAILED" in formatted
        assert "File not found" in formatted

    def test_format_truncation(self):
        big_output = "x" * 15000
        result = ToolResult(success=True, output=big_output)
        formatted = _format_tool_result("bash", result)
        assert "truncated" in formatted
        assert len(formatted) < 16000

    def test_format_with_metadata(self):
        result = ToolResult(success=True, output="ok", metadata={"exit_code": 0})
        formatted = _format_tool_result("bash", result)
        assert "Metadata" in formatted


class TestDecodeParametersCoercion:
    def test_decode_stringified_array(self):
        from server.toolkit.base import decode_parameters

        schema = {
            "type": "object",
            "properties": {
                "tasks": {"type": "array"},
                "action": {"type": "string"},
            },
            "required": ["action", "tasks"],
        }
        params = {"action": "write", "tasks": '[{"id": "t1", "title": "Audit"}]'}
        decoded = decode_parameters(schema, params)
        assert isinstance(decoded["tasks"], list)
        assert decoded["tasks"][0]["id"] == "t1"

    def test_decode_stringified_object(self):
        from server.toolkit.base import decode_parameters

        schema = {
            "type": "object",
            "properties": {
                "config": {"type": "object"},
            },
        }
        params = {"config": '{"key": "value"}'}
        decoded = decode_parameters(schema, params)
        assert isinstance(decoded["config"], dict)
        assert decoded["config"]["key"] == "value"


class TestTodoToolStringifiedTasks:
    @pytest.mark.asyncio
    async def test_todo_write_stringified_tasks_json(self):
        from server.toolkit.tools.todo import TodoTool

        tool = TodoTool()
        params = {
            "action": "write",
            "tasks": '[{"id": "t1", "title": "Check websockets", "priority": "high"}]',
        }
        res = await tool.execute(params, "")
        assert res.success is True
        assert "Check websockets" in res.output

    @pytest.mark.asyncio
    async def test_todo_write_stringified_items_json(self):
        from server.toolkit.tools.todo import TodoTool

        tool = TodoTool()
        params = {
            "action": "write",
            "tasks": ['{"id": "t2", "title": "Nested item", "priority": "medium"}'],
        }
        res = await tool.execute(params, "")
        assert res.success is True
        assert "Nested item" in res.output

    @pytest.mark.asyncio
    async def test_todo_write_invalid_item_does_not_wipe_state(self):
        from server.agents.todo_state import get_todo_state
        from server.toolkit.tools.todo import TodoTool

        tool = TodoTool()
        state = get_todo_state("")
        state.reset()

        # Seed an initial valid task
        seed_res = await tool.execute(
            {"action": "write", "tasks": [{"title": "Existing task"}]},
            "",
        )
        assert seed_res.success is True
        assert len(state.list()) == 1

        # Attempt write with invalid item
        res = await tool.execute(
            {"action": "write", "tasks": ["not valid json"]},
            "",
        )
        assert res.success is False
        assert "not valid JSON" in res.error

        # Ensure board was not wiped
        assert len(state.list()) == 1
        assert state.list()[0].title == "Existing task"

