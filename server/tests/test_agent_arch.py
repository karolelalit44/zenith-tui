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
