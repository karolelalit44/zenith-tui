"""Tests for agent architecture — templates, runtime, coordinator."""

import pytest

from server.agents.loop_detection import LoopDetector
from server.agents.runtime import AgentRuntime
from server.agents.templates import PromptBuilder, PromptTemplate

# ── PromptTemplate ───────────────────────────────────────────────────────

class TestPromptTemplate:
    def test_render_simple(self):
        t = PromptTemplate("Hello {{name}}")
        t.set("name", "World")
        assert t.render() == "Hello World"

    def test_render_multiple_vars(self):
        t = PromptTemplate("{{a}} and {{b}}")
        t.set("a", "X")
        t.set("b", "Y")
        assert t.render() == "X and Y"

    def test_variables_list(self):
        t = PromptTemplate("{{x}} {{y}} {{x}}")
        vars = t.variables
        assert set(vars) == {"x", "y"}

    def test_no_vars(self):
        t = PromptTemplate("no variables here")
        assert t.render() == "no variables here"
        assert t.variables == []


# ── PromptBuilder ────────────────────────────────────────────────────────

class TestPromptBuilder:
    @pytest.mark.asyncio
    async def test_build_system_prompt_no_templates(self):
        builder = PromptBuilder()
        result = await builder.build_system_prompt("coder", "/tmp")
        assert result == ""

    @pytest.mark.asyncio
    async def test_build_system_prompt_with_template(self):
        builder = PromptBuilder()
        builder.register("system_coder", PromptTemplate("You are assistant, root={{workspace_root}}, date={{date}}"))
        result = await builder.build_system_prompt("coder", "/tmp")
        assert "/tmp" in result
        assert "assistant" in result

    @pytest.mark.asyncio
    async def test_build_user_prompt_simple(self):
        builder = PromptBuilder()
        result = await builder.build_user_prompt("Hello")
        assert result == "Hello"

    @pytest.mark.asyncio
    async def test_build_user_prompt_with_repo_map(self):
        builder = PromptBuilder()
        result = await builder.build_user_prompt("Hello", repo_map="src/\n  main.py")
        assert "Repository Map" in result
        assert "src/" in result

    def test_load_templates_from_dir(self, temp_dir):
        (temp_dir / "system.md").write_text("System prompt")
        (temp_dir / "other.txt").write_text("ignored")
        builder = PromptBuilder()
        builder.load_templates(temp_dir)
        assert builder.get("system") is not None
        assert builder.get("other") is None  # .txt not loaded


# ── LoopDetector ─────────────────────────────────────────────────────────

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


# ── System Prompt Building & Direct Response Guidelines ─────────

class TestSystemPromptBuilding:
    def test_build_system_prompt_includes_direct_responses(self):
        from server.agents.prompts import build_system_prompt
        prompt = build_system_prompt(workspace_root="/tmp/test", mode="build")
        assert "Tool Usage Boundary" in prompt
        assert "without tools" in prompt

    def test_build_system_prompt_omits_text_tool_schemas(self):
        from server.agents.prompts import build_system_prompt
        dummy_schemas = [{"name": "file_read", "description": "Read file", "schema": {}}]
        prompt = build_system_prompt(workspace_root="/tmp/test", mode="build", tool_schemas=dummy_schemas)
        # Verify text schema block is omitted when native tools are present
        assert "<available_tools>" not in prompt



# ── AgentRuntime ABC ─────────────────────────────────────────────────────

class TestAgentRuntimeABC:
    def test_abc_cannot_instantiate(self):
        with pytest.raises(TypeError):
            AgentRuntime()
