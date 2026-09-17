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
async def test_failed_file_edit_duplicate_is_not_re_executed(test_config):
    """A failed file_edit call must be treated as a duplicate if the model repeats it unchanged."""
    from pathlib import Path

    root = Path(test_config.workspace_root)
    (root / "edit.txt").write_text("alpha\nbeta\n", encoding="utf-8")

    provider = _EchoProvider(
        [
            '```tool\n{"tool": "file_edit", "params": {"path": "edit.txt", "old_content": "gamma", "new_content": "delta"}}\n```',
            '```tool\n{"tool": "file_edit", "params": {"path": "edit.txt", "old_content": "gamma", "new_content": "delta"}}\n{"tool": "file_write", "params": {"path": "done.txt", "content": "ok"}}\n```',
            "Done.",
        ]
    )
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Fix the file", "s_failed_edit", []):
        events.append(event)

    edit_results = [
        e for e in events if e.kind == EventKind.TOOL_RESULT and e.data.get("tool") == "file_edit"
    ]
    assert len(edit_results) == 1, "the failed edit must not re-execute when repeated verbatim"
    assert edit_results[0].data.get("success") is False, "the first edit attempt must still run and fail"
    warnings = [e for e in events if e.kind == EventKind.WARNING]
    assert any(
        "file_edit(path=edit.txt) [failed]" in (e.data.get("message") or "")
        for e in warnings
    )
    assert (root / "done.txt").exists(), "new work after the duplicate edit must still run"
    assert events[-1].kind == EventKind.SUCCESS


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


@pytest.mark.asyncio
async def test_file_write_with_template_placeholder_rejected_and_reflected(test_config):
    """File write with template placeholders like YOUR_API_KEY_HERE is rejected and prompts reflection."""
    provider = _EchoProvider(
        [
            # Turn 1: Attempt to write code with a template stub
            '```tool\n{"tool": "file_write", "params": {"path": "config.py", "content": "API_KEY = \\"YOUR_API_KEY_HERE\\""}}\n```',
            # Turn 2: Upon rejection feedback, provide the real implementation
            '```tool\n{"tool": "file_write", "params": {"path": "config.py", "content": "API_KEY = \\"real-secret-123\\""}}\n```',
            # Turn 3: Complete
            "Saved config successfully.",
        ]
    )
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Write config", "s_placeholder", []):
        events.append(event)

    rejections = [e for e in events if e.kind == EventKind.WARNING and e.data.get("code") == "REJECTED"]
    assert rejections, "Placeholder write should trigger a REJECTED warning"
    assert "template placeholder" in rejections[0].data.get("message", "")

    target = Path(test_config.workspace_root) / "config.py"
    assert target.is_file(), "config.py should have been written on retry"
    assert "real-secret-123" in target.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_transitional_nudge_and_honest_completion(test_config):
    """If the model emits transitional commentary while tasks are pending, the loop nudges it to continue."""
    provider = _EchoProvider(
        [
            # Turn 1: Write todo list
            '```tool\n{"tool": "todo", "params": {"action": "write", "tasks": [{"id": "t1", "title": "Audit websocket", "status": "in_progress"}]}}\n```',
            # Turn 2: Transitional commentary without tool call
            "Now let me read the code to finish the audit.",
            # Turn 3: Final response after nudge
            "Audit findings: 0 unhandled exceptions found.",
        ]
    )
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Audit websocket", "s_nudge", []):
        events.append(event)

    # Provider is called:
    # 1: tool call (write todo)
    # 2: transitional commentary -> nudge 1
    # 3: first text response with todos still active -> nudge 2
    # 4: final text response -> nudges limit reached (2), loop cleanly stops
    assert provider.call_count == 4, f"Expected 4 calls (tool + 2 nudges + exit), got {provider.call_count}"
    success_events = [e for e in events if e.kind == EventKind.SUCCESS]
    assert success_events, "Turn should conclude with SUCCESS event"
    # Because task t1 was never completed in todo, completed should be False
    manifest = success_events[-1].data.get("manifest", {})
    assert manifest.get("completed") is False
    assert "active tasks remaining" in success_events[-1].data.get("message", "")


@pytest.mark.asyncio
async def test_conversational_response_no_nudge_without_todos(test_config):
    """If no active tasks exist, conversational responses starting with 'Let me' or 'I will' must not be nudged."""
    provider = _EchoProvider(["Let me explain how the architecture works in detail."])
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Explain the architecture", "s_conv", []):
        events.append(event)

    assert provider.call_count == 1, f"Expected exactly 1 call (no nudges), got {provider.call_count}"
    success_events = [e for e in events if e.kind == EventKind.SUCCESS]
    assert success_events, "Turn should conclude with SUCCESS event"
    manifest = success_events[-1].data.get("manifest", {})
    assert manifest.get("completed") is True


@pytest.mark.asyncio
async def test_plan_mode_with_pending_todos_marked_completed(test_config):
    """In PLAN_MODE, generating a todo list with pending tasks is the desired deliverable, so completed must be True."""
    from server.config.constants.agent import PLAN_MODE

    provider = _EchoProvider(
        [
            '```tool\n{"tool": "todo", "params": {"action": "write", "tasks": [{"id": "t1", "title": "Implement feature", "status": "pending"}]}}\n```',
            "Plan drafted and tasks created.",
        ]
    )
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Plan feature", "s_plan_todo", [], mode=PLAN_MODE):
        events.append(event)

    success_events = [e for e in events if e.kind == EventKind.SUCCESS]
    assert success_events
    manifest = success_events[-1].data.get("manifest", {})
    assert manifest.get("completed") is True


@pytest.mark.asyncio
async def test_prompt_mentioning_tools_auto_escalates_on_turn_1(test_config):
    """When a prompt mentions non-seed tools (e.g. 'todo', 'explore'), they are pre-escalated on Turn 1."""
    captured_tools = []

    class _CaptureProvider(_EchoProvider):
        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            captured_tools.append([t["function"]["name"] for t in (tools or [])])
            async for chunk in super().stream(messages, tools, tool_choice, response_format):
                yield chunk

    provider = _CaptureProvider(["I have finished."])
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry(config=test_config))

    events = []
    async for event in agent.process_prompt(
        "Use the todo tool to create a checklist and explore the repo.", "s_preseed", [], mode="build"
    ):
        events.append(event)

    assert captured_tools, "stream should have been called"
    turn1_tools = captured_tools[0]
    assert "todo" in turn1_tools, "todo should be in turn 1 tools when mentioned in prompt"
    assert "explore" in turn1_tools, "explore should be in turn 1 tools when mentioned in prompt"


@pytest.mark.asyncio
async def test_prompt_without_mentions_leaves_seed_unchanged(test_config):
    """A prompt that does not mention non-seed tools must not escalate them on Turn 1."""
    captured_tools = []

    class _CaptureProvider(_EchoProvider):
        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            captured_tools.append([t["function"]["name"] for t in (tools or [])])
            async for chunk in super().stream(messages, tools, tool_choice, response_format):
                yield chunk

    provider = _CaptureProvider(["I have finished."])
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry(config=test_config))

    events = []
    async for event in agent.process_prompt(
        "Refactor the CLI entrypoint and add tests.", "s_preseed_quiet", [], mode="build"
    ):
        events.append(event)

    assert captured_tools, "stream should have been called"
    turn1_tools = captured_tools[0]
    assert "explore" not in turn1_tools, "explore should stay unoffered when not mentioned"
    assert "websearch" not in turn1_tools, "websearch should stay unoffered when not mentioned"
    assert "file_read" in turn1_tools, "core seed tools must remain offered"


@pytest.mark.asyncio
async def test_substantive_answer_with_duplicate_tool_nudges_when_todos_remain(test_config):
    """When a turn emits a duplicate tool call and substantive text while todos are active, it must nudge instead of emergent-stopping."""
    provider = _EchoProvider(
        [
            # Turn 1: Write todo list with active task
            '```tool\n{"tool": "todo", "params": {"action": "write", "tasks": [{"id": "t1", "title": "Clean up files", "status": "in_progress"}]}}\n```',
            # Turn 2: Model re-emits same todo call with substantive progress sentence (>= 40 chars)
            'I will create the checklist and execute step 1 of the audit right away.\n```tool\n{"tool": "todo", "params": {"action": "write", "tasks": [{"id": "t1", "title": "Clean up files", "status": "in_progress"}]}}\n```',
            # Turn 3: Final response after nudge
            "Finished execution successfully.",
        ]
    )
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Clean up files", "s_dup_nudge", []):
        events.append(event)

    # 1: tool call (write todo)
    # 2: duplicate call + text with active todos -> nudge 1 (prevent early emergent stop)
    # 3: text response with todos still active -> nudge 2
    # 4: final text response -> nudges limit reached (2), loop cleanly stops
    assert provider.call_count == 4, f"Expected 4 calls (tool, dup+nudge 1, nudge 2, exit), got {provider.call_count}"
    success_events = [e for e in events if e.kind == EventKind.SUCCESS]
    assert success_events, "Turn should conclude with SUCCESS event"
    manifest = success_events[-1].data.get("manifest", {})
    assert manifest.get("completed") is False
    assert "active tasks remaining" in success_events[-1].data.get("message", "")


@pytest.mark.asyncio
async def test_read_only_tool_re_execution_allowed(test_config):
    """Read-only discovery tools like glob should not be blocked by duplicate call suppression."""
    provider = _EchoProvider(
        [
            # Turn 1: Initial glob
            '```tool\n{"tool": "glob", "params": {"pattern": "*.txt"}}\n```',
            # Turn 2: Write a file
            '```tool\n{"tool": "file_write", "params": {"path": "test.txt", "content": "hello"}}\n```',
            # Turn 3: Re-run the exact same glob to see the newly created file
            '```tool\n{"tool": "glob", "params": {"pattern": "*.txt"}}\n```',
            # Turn 4: Final response
            "All done.",
        ]
    )
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Find and create files", "s_ro_repeat", []):
        events.append(event)

    duplicate_warnings = [
        e for e in events if e.kind == EventKind.WARNING and e.data.get("code") == "DUPLICATE_CALL"
    ]
    assert not duplicate_warnings, "Read-only glob should never emit DUPLICATE_CALL warning"

    glob_calls = [
        e for e in events if e.kind == EventKind.TOOL_CALL and e.data.get("tool") == "glob"
    ]
    assert len(glob_calls) == 2, f"Expected 2 glob executions, got {len(glob_calls)}"




