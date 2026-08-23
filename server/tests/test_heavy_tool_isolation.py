"""Heavy-tool isolation (Gap #3): oversized tool outputs are summarized and
stored out-of-band instead of consuming the main context window."""

import pytest

from server.agents.loop import AgentLoop
from server.agents.session_workspace import read_heavy_output
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.toolkit.base import BaseTool, ToolResult
from server.toolkit.registry import ToolRegistry

HEAVY_TEXT = "line of output\n" * 4000  # ~64K chars, well over the 5000-token threshold


class _HeavyDumpTool(BaseTool):
    name = "heavy_dump"
    description = "Dumps a large blob of output"

    async def execute(self, params: dict, workspace_root: str) -> ToolResult:
        return ToolResult(success=True, output=HEAVY_TEXT)

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object"},
        }


class _SummarizingProvider:
    """Main provider whose ``complete`` also serves the heavy-output summarizer."""

    def __init__(self) -> None:
        self.model = "test-model"
        self._cumulative_usage = {}
        self._last_finish_reason = None
        self._last_native_tool_calls = []
        self.tool_calls = 0

    async def complete(self, messages, tools=None):
        last = messages[-1]["content"] if messages else ""
        if "Summarize the output of the tool call" in str(last):
            return "Terse summary: the dump contained N lines with filenames and error codes."
        self.tool_calls += 1
        if self.tool_calls == 1:
            return '```tool\n{"tool": "heavy_dump", "params": {}}\n```'
        return "All done. The dump was huge."

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        response = await self.complete(messages, tools)
        for char in response:
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["test-model"]


def _make_loop(temp_dir, provider, registry: ToolRegistry | None = None) -> AgentLoop:
    return AgentLoop(
        AppSettings(home_dir=str(temp_dir / "test.db"), workspace_root=str(temp_dir)),
        provider,
        tool_registry=registry,
    )


@pytest.mark.asyncio
async def test_heavy_output_is_summarized_and_stored(temp_dir):
    loop = _make_loop(temp_dir, _SummarizingProvider())
    result = ToolResult(success=True, output=HEAVY_TEXT)
    rel = await loop._maybe_summarize_heavy_output("s1", "bash", result)

    assert rel is not None
    stored = temp_dir / rel
    assert stored.exists()
    assert stored.read_text(encoding="utf-8") == HEAVY_TEXT
    assert read_heavy_output("s1", rel) == HEAVY_TEXT
    assert "Summary of output" in result.output
    assert "file_read" in result.output
    assert len(result.output) < 2000
    assert loop._heavy_tools_summarized == 1


@pytest.mark.asyncio
async def test_light_output_not_summarized(temp_dir):
    loop = _make_loop(temp_dir, _SummarizingProvider())
    result = ToolResult(success=True, output="tiny")
    assert await loop._maybe_summarize_heavy_output("s1", "bash", result) is None
    assert result.output == "tiny"
    assert loop._heavy_tools_summarized == 0


@pytest.mark.asyncio
async def test_failed_tool_not_summarized(temp_dir):
    loop = _make_loop(temp_dir, _SummarizingProvider())
    result = ToolResult(success=False, output=HEAVY_TEXT, error="boom")
    assert await loop._maybe_summarize_heavy_output("s1", "bash", result) is None
    assert result.output == HEAVY_TEXT


@pytest.mark.asyncio
async def test_file_read_excluded_from_heavy_summarization(temp_dir):
    loop = _make_loop(temp_dir, _SummarizingProvider())
    result = ToolResult(success=True, output=HEAVY_TEXT)
    assert await loop._maybe_summarize_heavy_output("s1", "file_read", result) is None
    assert result.output == HEAVY_TEXT


@pytest.mark.asyncio
async def test_full_output_re_readable_via_cached_read(temp_dir):
    loop = _make_loop(temp_dir, _SummarizingProvider())
    result = ToolResult(success=True, output=HEAVY_TEXT)
    rel = await loop._maybe_summarize_heavy_output("s1", "bash", result)
    assert rel is not None
    cached = loop._try_cached_read("s1", {"path": rel})
    assert cached == HEAVY_TEXT


@pytest.mark.asyncio
async def test_success_event_contains_heavy_tools_counter(temp_dir):
    registry = ToolRegistry()
    registry.register(_HeavyDumpTool())
    loop = _make_loop(temp_dir, _SummarizingProvider(), registry)

    events = [ev async for ev in loop.process_prompt("Run the dump", "s1", [], "build")]
    success = [ev for ev in events if ev.kind == EventKind.SUCCESS]
    assert success, "a success event must be emitted"
    assert success[0].data["tokenInfo"].get("heavy_tools_summarized", 0) >= 1

    tool_msgs = [
        ev.data.get("output", "")
        for ev in events
        if ev.kind == EventKind.TOOL_RESULT and ev.data.get("tool") == "heavy_dump"
    ]
    assert tool_msgs, "the heavy tool result must be emitted"
    assert "Summary of output" in tool_msgs[0]
    assert HEAVY_TEXT not in tool_msgs[0]
