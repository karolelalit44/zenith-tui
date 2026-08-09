import pytest

from server.agents.loop_detection import LoopDetector


class TestLoopDetector:
    def test_no_loop(self):
        det = LoopDetector(window_size=5, max_repeats=3)
        for i in range(4):
            det.record(f"tool_{i}", {"i": i}, f"result_{i}")
        assert not det.is_loop_detected()

    def test_loop_detected(self):
        det = LoopDetector(window_size=5, max_repeats=2)
        for _ in range(5):
            det.record("bash", {"command": "ls"}, "output")
        assert det.is_loop_detected()

    def test_reset(self):
        det = LoopDetector(window_size=5, max_repeats=2)
        for _ in range(3):
            det.record("bash", {"command": "ls"}, "output")
        det.reset()
        assert not det.is_loop_detected()
        assert det.window_fill == 0

    def test_window_fill(self):
        det = LoopDetector(window_size=3, max_repeats=10)
        det.record("a", {}, "")
        det.record("b", {}, "")
        assert det.window_fill == 2

    def test_consecutive_identical_loop_detected_before_window_fill(self):
        det = LoopDetector(window_size=10, max_repeats=2)
        for _ in range(3):
            det.record("bash", {"command": "ls"}, "output")
        assert det.is_loop_detected()

    def test_interleaved_identical_not_flagged_consecutive(self):
        det = LoopDetector(window_size=10, max_repeats=2)
        det.record("bash", {"command": "ls"}, "output")
        det.record("bash", {"command": "pwd"}, "output")
        det.record("bash", {"command": "ls"}, "output")
        assert not det.is_loop_detected()

    def test_reset_clears_consecutive_state(self):
        det = LoopDetector(window_size=10, max_repeats=2)
        for _ in range(3):
            det.record("bash", {"command": "ls"}, "output")
        det.reset()
        assert not det.is_loop_detected()
        det.record("bash", {"command": "ls"}, "output")
        assert not det.is_loop_detected()


class TestSystemPromptBuilding:
    def test_build_system_prompt_includes_direct_responses(self):
        from server.agents.prompts import build_system_prompt

        prompt = build_system_prompt(workspace_root="/tmp/test", mode="build")
        assert "General Queries" in prompt
        assert "without tool calls" in prompt

    def test_build_system_prompt_omits_text_tool_schemas(self):
        from server.agents.prompts import build_system_prompt

        dummy_schemas = [{"name": "file_read", "description": "Read file", "schema": {}}]
        prompt = build_system_prompt(
            workspace_root="/tmp/test", mode="build", tool_schemas=dummy_schemas
        )
        assert "<available_tools>" not in prompt

    def test_build_system_prompt_states_shell_constraint(self):
        """B1: the model is told the OS/shell and to use only that shell's syntax."""
        from server.agents.prompts import build_system_prompt

        prompt = build_system_prompt(workspace_root="/tmp/test", mode="build")
        assert "Shell:" in prompt
        assert "Write commands" in prompt

    def test_build_system_prompt_guides_batching_and_verification(self):
        """GAP1/GAP3: the model can batch independent calls and must verify new projects."""
        from server.agents.prompts import build_system_prompt

        prompt = build_system_prompt(workspace_root="/tmp/test", mode="build")
        assert "several independent tool calls" in prompt  # GAP1 batching
        assert "Verify Generated Projects" in prompt  # GAP3 verify scaffolded projects
        assert "run its tests" in prompt
        assert "Inspect Before Writing" in prompt  # X1 inspect target before writing
        assert "Environment Limits" in prompt  # X3 report failed verify steps honestly
        assert "A lean set of tool schemas" in prompt  # T2 discovery hint matches reality


class TestNoFilesCreatedWarning:
    async def _run_events(self, temp_dir, provider, tool_registry=None):
        from server.agents.loop import AgentLoop
        from server.config.settings import AppSettings

        agent = AgentLoop(
            AppSettings(db_path=str(temp_dir / "test.db"), workspace_root=str(temp_dir)),
            provider,
            tool_registry=tool_registry,
        )
        return [event async for event in agent.process_prompt("Hello", "s1", [], "build")]

    @pytest.mark.asyncio
    async def test_text_only_turn_has_no_no_files_warning(self, temp_dir):
        from server.domain.events import EventKind

        class TextOnlyProvider:
            def __init__(self):
                self.model = "test-model"
                self._cumulative_usage = {}
                self._last_finish_reason = None
                self._last_native_tool_calls = []

            async def complete(self, messages, tools=None):
                return "Just a text answer, no tools needed."

            async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
                yield ("Just a text answer, no tools needed.", None)

            async def validate(self):
                return True

        events = await self._run_events(temp_dir, TextOnlyProvider())
        codes = [e.data.get("code") for e in events if e.kind == EventKind.WARNING]
        assert "NO_FILES_CREATED" not in codes

    @pytest.mark.asyncio
    async def test_tool_using_turn_without_files_still_warns(self, temp_dir):
        from server.domain.events import EventKind
        from server.toolkit import create_default_registry

        class ToolUsingProvider:
            def __init__(self):
                self.call_count = 0
                self.model = "test-model"
                self._cumulative_usage = {}
                self._last_finish_reason = None
                self._last_native_tool_calls = []

            async def complete(self, messages, tools=None):
                self.call_count += 1
                if self.call_count == 1:
                    return '```tool\n{"tool": "file_read", "params": {"path": "x.txt"}}\n```'
                return "Done reading."

            async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
                response = await self.complete(messages)
                for char in response:
                    yield (char, None)

            async def validate(self):
                return True

        events = await self._run_events(temp_dir, ToolUsingProvider(), create_default_registry())
        codes = [e.data.get("code") for e in events if e.kind == EventKind.WARNING]
        assert "NO_FILES_CREATED" in codes
