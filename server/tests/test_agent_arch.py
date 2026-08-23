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
    def test_build_system_prompt_direct_answers_need_no_tools(self):
        from server.agents.prompts import build_system_prompt

        prompt = build_system_prompt(workspace_root="/tmp/test", mode="build")
        assert "general knowledge needs none" in prompt
        assert "Tools only when they add verified value" in prompt

    def test_build_system_prompt_omits_text_tool_schemas(self):
        from server.agents.prompts import build_system_prompt

        prompt = build_system_prompt(workspace_root="/tmp/test", mode="build")
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
        assert "Batch independent calls" in prompt  # GAP1 batching
        assert "Never claim unrun verification" in prompt  # X3 report failed verify steps honestly
        assert "A lean set of tool schemas" in prompt  # T2 discovery hint matches reality

    def test_build_and_plan_modes_use_dedicated_instructions(self):
        from server.agents.prompts import build_system_prompt

        plan = build_system_prompt(workspace_root="/tmp/test", mode="plan")
        build = build_system_prompt(workspace_root="/tmp/test", mode="build")
        assert "## BOUNDARY" in plan
        assert "plan.md" in plan and "todo.md" in plan
        assert "## PRINCIPLES" in build
        assert "## BOUNDARY" not in build
        assert "Only writable files are plan.md and todo.md" not in build

    def test_build_system_prompt_classifies_intent(self):
        """Intent detection must be explicit: EXECUTE vs PLAN/DESIGN vs QUESTION."""
        from server.agents.prompts import build_system_prompt

        prompt = build_system_prompt(workspace_root="/tmp/test", mode="build")
        assert "## INTENT" in prompt
        assert "Execute by default" in prompt
        assert "provide a plan without modifying anything" in prompt
        assert "don't modify anything" in prompt
        assert "BUILD mode: EXECUTE" in prompt

    def test_build_system_prompt_enforces_exact_names(self):
        """Fidelity regression: never re-spell the user's names; honor exact spellings."""
        from server.agents.prompts import build_system_prompt

        prompt = build_system_prompt(workspace_root="/tmp/test", mode="build")
        assert "exact names, paths, and spellings" in prompt
        assert "Don't invent facts or requirements" in prompt

    def test_build_system_prompt_anti_fabrication_and_scope(self):
        """Regression: never invent facts/dates; create exactly what was asked (no invented variants); verify content."""
        from server.agents.prompts import build_system_prompt

        prompt = build_system_prompt(workspace_root="/tmp/test", mode="build")
        assert "Never fabricate facts, dates, or values" in prompt
        assert "no invented variants or extra files" in prompt
        assert "Verify content, not tool success" in prompt

    def test_build_system_prompt_resolves_conflicts_and_scales_depth(self):
        """Regression: latest user message wins on conflict; reply depth matches the request."""
        from server.agents.prompts import build_system_prompt

        prompt = build_system_prompt(workspace_root="/tmp/test", mode="build")
        assert "latest user message wins" in prompt
        assert "Match the request" in prompt

    def test_build_system_prompt_is_task_agnostic(self):
        """Regression: the agent is general-purpose, not narrowed to coding tasks."""
        from server.agents.prompts import build_system_prompt

        prompt = build_system_prompt(workspace_root="/tmp/test", mode="build")
        assert "code, configuration, documents, data" in prompt
        assert "Not a task-specific tool" in prompt
        assert "Follow-ups" in prompt
        assert "repository" not in prompt

    def test_plan_system_prompt_classifies_intent(self):
        """In plan mode an execution-sounding request must become a PLAN, not code."""
        from server.agents.prompts import build_system_prompt

        prompt = build_system_prompt(workspace_root="/tmp/test", mode="plan")
        assert "PLANNING ONLY" in prompt
        assert "never implement or modify" in prompt
        assert "## BOUNDARY" in prompt
        assert "unresolved decisions" in prompt

    def test_plan_block_defers_to_latest_user_message(self):
        """A previously approved plan must not override a newer, conflicting user intent."""
        from server.agents.context import ContextManager
        from server.config.settings import AppSettings

        cm = ContextManager(AppSettings(workspace_root="/tmp/test", home_dir="/tmp/test.db"))
        from server.domain.message import Message

        messages = cm.build_messages(
            history=[Message(session_id="s1", role="user", content="Earlier prompt")],
            system_prompt="sys",
            new_prompt="Actually do X instead of the plan.",
            model="gemini-3.5-flash-lite",
            plan_block="PLAN: do Y.",
        )
        plan_msgs = [
            m for m in messages if m.get("role") == "system" and "plan_to_execute" in m["content"]
        ]
        assert plan_msgs, "plan block must be injected"
        assert "latest message is the authoritative intent" in plan_msgs[0]["content"]
        assert "follow the latest message" in plan_msgs[0]["content"]


class TestNoFilesCreatedWarning:
    async def _run_events(self, temp_dir, provider, tool_registry=None):
        from server.agents.loop import AgentLoop
        from server.config.settings import AppSettings

        agent = AgentLoop(
            AppSettings(home_dir=str(temp_dir / "test.db"), workspace_root=str(temp_dir)),
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
