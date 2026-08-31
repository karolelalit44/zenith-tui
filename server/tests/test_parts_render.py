"""Module 09 additive interface-lock: clean Part content delivery.

Reference: opencode AnyPart (TextPart / ReasoningPart / ToolCallPart /
ToolResultPart) and codex EventMsg content deltas. These ride inside the
existing MESSAGE event under data.parts with a rendered data.text fallback,
so the transport/TUI are unchanged (G5). The MAX_EVENT_OUTPUT preview hack and
invented event kinds remain for Phase 3.
"""

from server.domain.events import EventKind
from server.providers.responder import (
    PartKind,
    error_part,
    parts_message,
    reasoning_part,
    render_parts_text,
    text_part,
    tool_call_part,
    tool_result_part,
)


class TestPartFactories:
    def test_text_part(self):
        p = text_part("hello", partial=True)
        assert p.type is PartKind.TEXT
        assert p.text == "hello"
        assert p.partial is True

    def test_reasoning_part(self):
        p = reasoning_part("thinking...", duration_ms=5)
        assert p.type is PartKind.REASONING
        assert p.text == "thinking..."
        assert p.duration_ms == 5

    def test_tool_call_part(self):
        p = tool_call_part("bash", {"command": "ls"})
        assert p.type is PartKind.TOOL_CALL
        assert p.tool == "bash"
        assert p.input == {"command": "ls"}

    def test_tool_result_part(self):
        p = tool_result_part("file_read", output="x" * 20000)
        assert p.type is PartKind.TOOL_RESULT
        assert p.tool == "file_read"
        assert "truncated" in p.output  # full-but-truncated, not a tiny preview

    def test_error_part(self):
        p = error_part("boom")
        assert p.type is PartKind.ERROR
        assert p.text == "boom"


class TestRenderPartsText:
    def test_text_and_tool_composition(self):
        parts = [
            text_part("Here is the result."),
            tool_call_part("bash", {}),
            tool_result_part("bash", output="done"),
        ]
        text = render_parts_text(parts)
        assert "Here is the result." in text
        assert "Executing bash..." in text
        assert "done" in text

    def test_mixed_sections_separated(self):
        text = render_parts_text([text_part("a"), reasoning_part("r")])
        assert "\n\n" in text
        assert text == "a\n\nr"


class TestPartsMessage:
    def test_event_shape_preserves_transport(self):
        ev = parts_message([text_part("hi")], "s1")
        assert ev.kind is EventKind.MESSAGE
        assert ev.session_id == "s1"
        assert "parts" in ev.data
        assert len(ev.data["parts"]) == 1
        assert ev.data["parts"][0]["type"] == "text"
        assert ev.data["text"] == "hi"

    def test_serialized_parts_are_dicts(self):
        parts = [reasoning_part("r"), tool_call_part("grep", {"p": "x"})]
        ev = parts_message(parts, "s2")
        assert all(isinstance(p, dict) for p in ev.data["parts"])
        kinds = [p["type"] for p in ev.data["parts"]]
        assert kinds == ["reasoning", "tool-call"]

    def test_partial_and_iteration(self):
        ev = parts_message([text_part("a", partial=True)], "s3", partial=True, iteration=2)
        assert ev.data["partial"] is True
        assert ev.data["iteration"] == 2
