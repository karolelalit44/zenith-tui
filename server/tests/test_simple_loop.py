"""Tests for the additive SimpleLoop (module 01, turn/loop redesign).

Covers the three core design guarantees from
``agent_engine_redesign/turn/feature.md``:
- Stop is emergent: no tool calls -> the loop stops.
- Tool-then-stop: a tool call executes (with hooks), then the model's next
  plain response ends the turn.
- Doom-loop guard: DOOM_LOOP_THRESHOLD consecutive identical (name + input)
  tool calls emit a DOOM_LOOP ask and end the turn, instead of looping forever.
"""

from pathlib import Path

import pytest

from server.agents.simple_loop import SimpleLoop
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.providers.base import BaseProvider
from server.toolkit import create_default_registry


class _EchoProvider(BaseProvider):
    """Returns the canned next response per call; drives stream() from complete()."""

    def __init__(self, responses):
        super().__init__("echo", "echo-model")
        self.responses = list(responses)
        self.call_count = 0

    async def complete(self, messages, tools=None):
        self.call_count += 1
        i = min(self.call_count - 1, len(self.responses) - 1)
        return self.responses[i]

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        response = await self.complete(messages, tools)
        for char in response:
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["echo-model"]


@pytest.fixture
def test_config(temp_dir):
    return AppSettings(
        providers={"test": ProviderConfig(model="test-model", is_active=True)},
        active_provider="test",
        home_dir=str(temp_dir / "test.db"),
        workspace_root=str(temp_dir),
    )


@pytest.mark.asyncio
async def test_emergent_stop_without_tool_calls(test_config):
    """No tool calls in the response => the loop stops cleanly."""
    provider = _EchoProvider(["Just answering, no tools needed."])
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Explain something", "s1", []):
        events.append(event)

    assert provider.call_count == 1, "loop must stop after the first answer"
    messages = [e for e in events if e.kind == EventKind.MESSAGE]
    assert messages, "response text should be emitted"
    assert "Just answering" in messages[-1].data.get("text", "")
    tool_calls = [e for e in events if e.kind == EventKind.TOOL_CALL]
    assert not tool_calls, "no tool executed for a pure answer"


@pytest.mark.asyncio
async def test_tool_then_stop_executes_and_ends(test_config):
    """A tool call executes, then the no-call response ends the turn."""
    provider = _EchoProvider(
        [
            '```tool\n{"tool": "file_write", "params": {"path": "hello.txt", "content": "hi"}}\n```',
            "Created the file as requested.",
        ]
    )
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Create hello.txt with hi", "s2", []):
        events.append(event)

    tool_calls = [e for e in events if e.kind == EventKind.TOOL_CALL]
    tool_results = [e for e in events if e.kind == EventKind.TOOL_RESULT]
    assert tool_calls, "a tool_call event must be emitted"
    assert tool_results, "a tool_result event must be emitted"
    assert provider.call_count == 2, "two stream calls: tool turn + final stop"

    target = test_config.workspace_root + "/hello.txt"
    import os

    assert os.path.exists(target), "file_write should have created the file"


@pytest.mark.asyncio
async def test_doom_loop_guard_stops_turn(test_config):
    """Repeated identical tool calls hit DOOM_LOOP_THRESHOLD and end the turn."""
    call = (
        '```tool\n{"tool": "file_read", "params": {"path": "same.txt"}}\n```'
    )
    # Always emit the SAME tool call -> consecutive identical -> doom guard.
    provider = _EchoProvider([call])
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Keep reading", "s3", []):
        events.append(event)

    doom = [e for e in events if e.kind == EventKind.WARNING and e.data.get("code") == "DOOM_LOOP"]
    assert doom, "DOOM_LOOP warning must be emitted after repeated identical calls"
    success = [e for e in events if e.kind == EventKind.SUCCESS]
    assert success, "turn should still end with a SUCCESS event"


@pytest.mark.asyncio
async def test_file_write_with_bracketed_doc_text_succeeds(test_config):
    """Writing documentation with bracketed phrases like [List Updated] succeeds without rejection."""
    prd_content = "# School PRD\n\n- [List Updated] Teacher-Class Mapping\n- [File: models.py]\n"
    provider = _EchoProvider(
        [
            f'```tool\n{{"tool": "file_write", "params": {{"path": "prd.md", "content": {prd_content!r}}}}}\n```',
            "Created PRD document successfully.",
        ]
    )
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Create PRD", "s_prd", []):
        events.append(event)

    warnings = [e for e in events if e.kind == EventKind.WARNING and e.data.get("code") == "REJECTED"]
    assert not warnings, f"No tool rejection should occur for normal bracketed text: {warnings}"

    target = Path(test_config.workspace_root) / "prd.md"
    assert target.is_file(), "file_write should have created prd.md"
    assert target.read_text(encoding="utf-8").strip() == prd_content.strip()


@pytest.mark.asyncio
async def test_rejected_tool_call_triggers_reflection_retry(test_config):
    """When a tool call is rejected, the loop must not break early on prior turn text; it must allow reflection."""
    provider = _EchoProvider(
        [
            # Turn 1: Initial greeting and explore call
            'I will inspect the workspace and create the file.\n\n```tool\n{"tool": "list_dir", "params": {"path": "."}}\n```',
            # Turn 2: Rejected tool call (file_edit without old_content), no text
            '```tool\n{"tool": "file_edit", "params": {"path": "test.txt", "old_content": "", "new_content": "fixed"}}\n```',
            # Turn 3: Correction after receiving tool rejection feedback
            '```tool\n{"tool": "file_write", "params": {"path": "test.txt", "content": "fixed"}}\n```',
            # Turn 4: Final completion message
            "All done! The file has been written.",
        ]
    )
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Write test file", "s_reflect", []):
        events.append(event)

    rejections = [e for e in events if e.kind == EventKind.WARNING and e.data.get("code") == "REJECTED"]
    assert rejections, "Rejection warning should be emitted for invalid tool call"
    assert provider.call_count == 4, f"Expected 4 calls (explore, rejected, corrected, finish), got {provider.call_count}"

    target = Path(test_config.workspace_root) / "test.txt"
    assert target.is_file(), "file_write in turn 3 should have created test.txt"
    assert target.read_text(encoding="utf-8") == "fixed"

