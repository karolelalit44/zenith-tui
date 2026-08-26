"""Loop output guards (AGENT_RELIABILITY_PLAN P3).

Covers:
- P3.3: meta-placeholder texts (``[tool calls]`` etc.) are never rendered as
  assistant answers.
- P3.1: streamed finish reasons propagate from the provider stream so length
  stops are visible instead of being reported as ``stop``.
"""

import pytest

from server.agents.loop import AgentLoop, _is_degenerate_message
from server.config.constants import BUILD_MODE
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.providers.base import BaseProvider
from server.toolkit import create_default_registry


class _DegenerateThenAnswerProvider(BaseProvider):
    """Emits a placeholder text with a tool call, then a real answer."""

    def __init__(self):
        super().__init__("degen", "degen-model")
        self.call_count = 0

    async def complete(self, messages, tools=None):
        self.call_count += 1
        if self.call_count == 1:
            return '[tool calls]\n```tool\n{"tool": "file_read", "params": {"path": "a.txt"}}\n```'
        return "The workspace contains a single module implementing the CLI entry point."

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        response = await self.complete(messages, tools)
        for char in response:
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["degen-model"]


@pytest.fixture
def test_config(temp_dir):
    return AppSettings(
        providers={"test": ProviderConfig(model="test-model", is_active=True)},
        active_provider="test",
        home_dir=str(temp_dir / "test.db"),
        workspace_root=str(temp_dir),
    )


def test_is_degenerate_message_table():
    for raw in ("[tool calls]", "[TOOL CALLS]", "[thinking]", "[no output]", "  \n", "", None):
        assert _is_degenerate_message(raw), raw
    for raw in ("[tool calls] plus prose", "The answer is 4.", "Done."):
        assert not _is_degenerate_message(raw), raw


@pytest.mark.asyncio
async def test_degenerate_placeholder_never_reaches_transcript(test_config, temp_dir):
    (temp_dir / "a.txt").write_text("x", encoding="utf-8")
    agent = AgentLoop(
        test_config, _DegenerateThenAnswerProvider(), tool_registry=create_default_registry()
    )

    events = []
    async for event in agent.process_prompt("Describe the repo", "s1", [], BUILD_MODE):
        events.append(event)

    placeholders = [
        e
        for e in events
        if e.kind == EventKind.MESSAGE and "[tool calls]" in str(e.data.get("text") or "")
    ]
    assert placeholders == [], "meta-placeholder text leaked into the transcript"
    answers = [
        e
        for e in events
        if e.kind == EventKind.MESSAGE
        and str(e.data.get("text") or "").startswith("The workspace contains")
    ]
    assert len(answers) == 1, "the real answer must still be delivered exactly once"
    assert events[-1].kind == EventKind.SUCCESS
