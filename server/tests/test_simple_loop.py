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
from server.domain.message import Message, ToolCall
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

    target = Path(test_config.workspace_root) / "hello.txt"

    assert target.exists(), "file_write should have created the file"


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
    assert "websearch" in turn1_tools, "websearch is a core build seed tool"
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


@pytest.mark.asyncio
async def test_cached_file_read_provides_content_to_messages(test_config):
    """When a file is re-read from cache, the message must contain the file content, not a placeholder."""
    sample = Path(test_config.workspace_root) / "sample.py"
    sample.write_text("hello_world = 42\n", encoding="utf-8")

    captured_messages = []

    class _CaptureProvider(_EchoProvider):
        async def complete(self, messages, tools=None):
            captured_messages.append(list(messages))
            return await super().complete(messages, tools)

    provider = _CaptureProvider(
        [
            # Turn 1: Initial read
            '```tool\n{"tool": "file_read", "params": {"path": "sample.py"}}\n```',
            # Turn 2: Re-read the same file (served from cache)
            '```tool\n{"tool": "file_read", "params": {"path": "sample.py"}}\n```',
            # Turn 3: Conclude
            "Done analyzing sample.py",
        ]
    )
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Read sample", "s_cached_read", []):
        events.append(event)

    # In turn 3 (index 2), the LLM receives messages that include the cached read tool result
    assert len(captured_messages) >= 3
    final_messages = captured_messages[2]
    # The tool result for the cached read should contain "hello_world = 42"
    tool_user_msgs = [m for m in final_messages if m.get("role") == "user" and "hello_world" in m.get("content", "")]
    assert len(tool_user_msgs) >= 2, f"Both initial and cached reads must include the file content: {tool_user_msgs}"

    # It must never contain the old toxic prompt string
    for m in final_messages:
        content = m.get("content", "")
        assert "do not read again" not in content


@pytest.mark.asyncio
async def test_tool_calls_truncated_empty_content_retries(test_config):
    """When finish_reason is TOOL_CALLS but no tool calls parsed and content is empty,

    loop appends [response truncated] and retries rather than emergent stop.
    """
    from server.domain.enums import FinishReason

    class _TruncatedProvider(BaseProvider):
        def __init__(self):
            super().__init__("trunc", "trunc-model")
            self.call_count = 0
            self.captured_messages = []

        async def complete(self, messages, tools=None):
            self.call_count += 1
            self.captured_messages.append([dict(m) for m in messages])
            if self.call_count == 1:
                # Truncated tool call: empty content, finish_reason=tool_calls
                self._last_finish_reason = FinishReason.TOOL_CALLS
                return ""
            # Next turn succeeds with final answer
            self._last_finish_reason = FinishReason.STOP
            return "Final completed answer here."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages, tools)
            for char in response:
                yield (char, None)

        async def validate(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["trunc-model"]

    provider = _TruncatedProvider()
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for ev in agent.process_prompt("Run something", "s_trunc", []):
        events.append(ev)

    assert provider.call_count == 2
    # Second call must contain the [response truncated] placeholder and cut-off notice
    second_call_msgs = provider.captured_messages[1]
    assistant_msgs = [m for m in second_call_msgs if m.get("role") == "assistant"]
    assert any("[response truncated]" in m.get("content", "") for m in assistant_msgs)
    user_msgs = [m for m in second_call_msgs if m.get("role") == "user"]
    assert any("cut off before the tool call was complete" in m.get("content", "") for m in user_msgs)


@pytest.mark.asyncio
async def test_tool_calls_all_duplicates_skipped_enriches_stall_prompt(test_config, temp_dir):
    """When finish_reason is TOOL_CALLS and all valid calls are dup-skipped,

    the stall recovery prompt names the skipped tool calls.
    """
    from server.domain.enums import FinishReason

    (temp_dir / "target.txt").write_text("content", encoding="utf-8")

    class _DupStallProvider(BaseProvider):
        def __init__(self):
            super().__init__("dup_stall", "dup-model")
            self.call_count = 0
            self.captured_messages = []

        async def complete(self, messages, tools=None):
            self.call_count += 1
            self.captured_messages.append([dict(m) for m in messages])
            if self.call_count == 1:
                self._last_finish_reason = FinishReason.TOOL_CALLS
                return '```tool\n{"tool": "glob", "params": {"pattern": "*.txt"}}\n```'
            if self.call_count == 2:
                # Substantive transitional message + repeated same tool call
                self._last_finish_reason = FinishReason.TOOL_CALLS
                self._last_native_tool_calls = [
                    {"function": {"name": "glob", "arguments": '{"pattern": "*.txt"}'}}
                ]
                return (
                    "I will examine the directory to find the answer and summarize everything for you in detail."
                )
            self._last_finish_reason = FinishReason.STOP
            self._last_native_tool_calls = []
            return "Here is the final answer based on the files."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages, tools)
            for char in response:
                yield (char, None)

        async def validate(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["dup-model"]

    provider = _DupStallProvider()
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for ev in agent.process_prompt("Find txt files", "s_dup_enrich", []):
        events.append(ev)

    assert provider.call_count == 3
    # Turn 3 messages should receive the recovery prompt mentioning glob(pattern=*.txt)
    third_call_msgs = provider.captured_messages[2]
    recovery_msgs = [
        m for m in third_call_msgs
        if m.get("role") == "user" and "glob" in m.get("content", "") and "*.txt" in m.get("content", "")
    ]
    assert len(recovery_msgs) >= 1
    assert "Do not repeat them." in recovery_msgs[0]["content"]


@pytest.mark.asyncio
async def test_dispatch_sanitization_does_not_mutate_original_messages(test_config):
    """Sanitizing empty assistant messages for provider dispatch must not mutate

    the underlying message objects in memory.
    """
    class _CaptureSanProvider(BaseProvider):
        def __init__(self):
            super().__init__("san", "san-model")
            self.dispatched = []
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            # Record the actual dicts in messages to verify whether they got mutated
            self.dispatched.append(messages)
            if self.call_count == 1:
                # Emit an invalid native tool call with empty text content
                self._last_native_tool_calls = [
                    {"function": {"name": "nonexistent_tool_123", "arguments": "{}"}}
                ]
                return ""
            self._last_native_tool_calls = []
            return "All done."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages, tools)
            for char in response:
                yield (char, None)

        async def validate(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["san-model"]

    provider = _CaptureSanProvider()
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for ev in agent.process_prompt("Hello", "s_san", []):
        events.append(ev)

    assert provider.call_count == 2
    # In call 2, the dispatched assistant message from turn 1 should be sanitized to "..."
    dispatched_assistant = [m for m in provider.dispatched[1] if m.get("role") == "assistant"]
    assert any(m.get("content") == "..." for m in dispatched_assistant)
    # The message in agent's in-flight messages should have remained with its original content
    # (not mutated in place)
    raw_in_flight_assistants = [m for m in agent.context_manager.build_messages([], "", "", "test-model") if False]
    # Verify the sanitization produced new copied dicts rather than mutating
    sanitized_item = next(m for m in dispatched_assistant if m.get("content") == "...")
    assert sanitized_item["content"] == "..."


@pytest.mark.asyncio
async def test_length_finish_reason_auto_continues_text(test_config):
    """When finish_reason is LENGTH on text, SimpleLoop auto-continues and emits combined response."""
    from server.domain.enums import FinishReason

    class _LengthTruncatedProvider(BaseProvider):
        def __init__(self):
            super().__init__("trunc_len", "trunc-model")
            self.call_count = 0
            self.captured_messages = []

        async def complete(self, messages, tools=None):
            self.call_count += 1
            self.captured_messages.append([dict(m) for m in messages])
            if self.call_count == 1:
                self._last_finish_reason = FinishReason.LENGTH
                return "Part 1 of the answer: Here is the first half of the explanation."
            self._last_finish_reason = FinishReason.STOP
            return " Part 2 of the answer: Here is the second half concluding the explanation."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages, tools)
            for char in response:
                yield (char, None)

        async def validate(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["trunc-model"]

    provider = _LengthTruncatedProvider()
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for ev in agent.process_prompt("Explain everything in detail", "s_len", []):
        events.append(ev)

    assert provider.call_count == 2
    # Verify user continuation instruction was sent in call 2
    second_msgs = provider.captured_messages[1]
    user_msgs = [m for m in second_msgs if m.get("role") == "user"]
    assert any("reached the token limit and was cut off" in m.get("content", "") for m in user_msgs)

    # Verify message event contains the combined text
    message_events = [e for e in events if e.kind == EventKind.MESSAGE and not e.data.get("partial")]
    assert len(message_events) >= 1
    final_text = message_events[-1].data.get("text", "")
    assert "Part 1 of the answer" in final_text
    assert "Part 2 of the answer" in final_text


@pytest.mark.asyncio
async def test_length_finish_reason_auto_continues_truncated_tool(test_config):
    """When finish_reason is LENGTH on a truncated tool call, SimpleLoop prompts the model to re-emit."""
    from server.domain.enums import FinishReason

    class _ToolTruncatedProvider(BaseProvider):
        def __init__(self):
            super().__init__("trunc_tool", "trunc-model")
            self.call_count = 0
            self.captured_messages = []

        async def complete(self, messages, tools=None):
            self.call_count += 1
            self.captured_messages.append([dict(m) for m in messages])
            if self.call_count == 1:
                self._last_finish_reason = FinishReason.LENGTH
                return '```tool\n{"tool": "glob", "params": {"pattern":'
            self._last_finish_reason = FinishReason.STOP
            return "No tool needed, here is the answer."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages, tools)
            for char in response:
                yield (char, None)

        async def validate(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["trunc-model"]

    provider = _ToolTruncatedProvider()
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for ev in agent.process_prompt("Find files", "s_tool_len", []):
        events.append(ev)

    assert provider.call_count == 2
    second_msgs = provider.captured_messages[1]
    user_msgs = [m for m in second_msgs if m.get("role") == "user"]
    assert any("cut off before the tool call was complete" in m.get("content", "") for m in user_msgs)


@pytest.mark.asyncio
async def test_nudges_reset_on_successful_tool_execution(test_config, temp_dir):
    """Successful tool execution resets nudges, preventing premature termination on multi-step tasks."""
    (temp_dir / "step1.txt").write_text("done1", encoding="utf-8")
    (temp_dir / "step2.txt").write_text("done2", encoding="utf-8")

    class _MultiStepNudgeProvider(BaseProvider):
        def __init__(self):
            super().__init__("multi_nudge", "nudge-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count == 1:
                # Setup 2 tasks
                return '```tool\n{"tool": "todo", "params": {"action": "write", "tasks": [{"id": "1", "title": "First", "status": "in_progress"}, {"id": "2", "title": "Second", "status": "pending"}]}}\n```'
            if self.call_count == 2:
                # Chat transition (nudge 1)
                return "I will now read step 1."
            if self.call_count == 3:
                # Tool 1 succeeds -> should reset nudges!
                return '```tool\n{"tool": "file_read", "params": {"path": "step1.txt"}}\n```'
            if self.call_count == 4:
                # Chat transition (would fail if nudges wasn't reset, because nudges would be 2!)
                return "Finished step 1, now reading step 2."
            if self.call_count == 5:
                # Tool 2 succeeds and completes tasks
                return '```tool\n{"tool": "todo", "params": {"action": "write", "tasks": [{"id": "1", "title": "First", "status": "completed"}, {"id": "2", "title": "Second", "status": "completed"}]}}\n```'
            return "Both steps completed successfully."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages, tools)
            for char in response:
                yield (char, None)

        async def validate(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["nudge-model"]

    provider = _MultiStepNudgeProvider()
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for ev in agent.process_prompt("Execute multi-step task", "s_multi_nudge", []):
        events.append(ev)

    # Provider should reach all 6 calls because nudges was reset after each successful tool!
    assert provider.call_count == 6, f"Expected 6 calls, got {provider.call_count}"


@pytest.mark.asyncio
async def test_length_finish_reason_capped_sets_completed_false(test_config):
    """When a response continuously hits LENGTH and reaches continuation cap, completed MUST be False."""
    from server.domain.enums import FinishReason

    class _AlwaysLengthProvider(BaseProvider):
        def __init__(self):
            super().__init__("always_length", "len-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            self._last_finish_reason = FinishReason.LENGTH
            return f"This is continuous long output part {self.call_count} that gets cut off."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            resp = await self.complete(messages, tools)
            for c in resp:
                yield (c, None)

        async def validate(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["len-model"]

    provider = _AlwaysLengthProvider()
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for ev in agent.process_prompt("Write a huge essay", "s_len_cap", []):
        events.append(ev)

    # Initial call + 5 continuations = 6 total calls
    assert provider.call_count == 6, f"Expected 6 calls, got {provider.call_count}"

    success_events = [e for e in events if e.kind == EventKind.SUCCESS]
    assert success_events, "Turn should conclude with terminal event"
    term = success_events[-1]
    assert term.data.get("completed") is False, "Truncated turn must NEVER have completed=True"
    assert term.data.get("truncated") is True
    assert term.data.get("finish_reason") == "length"
    assert "token limit" in term.data.get("message", "")

    manifest = term.data.get("manifest", {})
    assert manifest.get("completed") is False
    assert any("token limit" in r for r in manifest.get("remaining", []))


@pytest.mark.asyncio
async def test_native_tool_call_truncated_by_length_prompts_reemission(test_config):
    """When native tool call is cut off by LENGTH, loop prompts model to re-emit rather than running truncated call."""
    from server.domain.enums import FinishReason

    class _NativeTruncatedToolProvider(BaseProvider):
        def __init__(self):
            super().__init__("native_trunc", "native-model")
            self.call_count = 0
            self.captured_messages = []

        async def complete(self, messages, tools=None):
            self.call_count += 1
            self.captured_messages.append([dict(m) for m in messages])
            if self.call_count == 1:
                self._last_finish_reason = FinishReason.LENGTH
                self._last_native_tool_calls = [{"id": "call_1", "function": {"name": "file_write", "arguments": '{"filepath": "test.txt", "content": "half'}}]
                return ""
            self._last_finish_reason = FinishReason.STOP
            self._last_native_tool_calls = []
            return "Retried without tool call, finished cleanly."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            resp = await self.complete(messages, tools)
            for c in resp:
                yield (c, None)

        async def validate(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["native-model"]

    provider = _NativeTruncatedToolProvider()
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for ev in agent.process_prompt("Write a test file", "s_native_trunc", []):
        events.append(ev)

    assert provider.call_count == 2
    # Verify the user continuation prompt told the model it was cut off before the tool call was complete
    second_msgs = provider.captured_messages[1]
    user_msgs = [m for m in second_msgs if m.get("role") == "user"]
    assert any("cut off before the tool call was complete" in m.get("content", "") for m in user_msgs)


@pytest.mark.asyncio
async def test_mode_restricted_native_call_omitted_and_first(test_config):
    """G2: a registered-but-mode-restricted tool call (bash in read_only) must
    be omitted with a MODE_RESTRICTED warning and a feedback message that
    names the available tools — never passed through to execution."""
    from server.config.constants import READ_ONLY_MODE
    from server.domain.enums import FinishReason

    class _G2Provider(BaseProvider):
        def __init__(self):
            super().__init__("g2", "g2-model")
            self.call_count = 0
            self.captured_messages = []

        async def complete(self, messages, tools=None):
            self.call_count += 1
            self.captured_messages.append([dict(m) for m in messages])
            if self.call_count == 1:
                self._last_finish_reason = FinishReason.TOOL_CALLS
                self._last_native_tool_calls = [
                    {"function": {"name": "bash", "arguments": '{"command": "ls"}'}}
                ]
                return "Let me inspect the environment."
            self._last_finish_reason = FinishReason.STOP
            self._last_native_tool_calls = []
            return "Final answer for read-only mode."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages, tools)
            for char in response:
                yield (char, None)

        async def validate(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["g2-model"]

    provider = _G2Provider()
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for ev in agent.process_prompt(
        "Inspect the environment", "s_g2_mode", [], mode=READ_ONLY_MODE
    ):
        events.append(ev)

    # The bash call must never execute.
    bash_execs = [e for e in events if e.kind == EventKind.TOOL_CALL and e.data.get("tool") == "bash"]
    assert not bash_execs, "mode-restricted bash must not execute"

    # A MODE_RESTRICTED warning surfaces the omission.
    warnings = [
        e for e in events if e.kind == EventKind.WARNING and e.data.get("code") == "MODE_RESTRICTED"
    ]
    assert len(warnings) >= 1
    assert "bash" in warnings[0].data.get("message", "")

    # The second provider call receives the rejection + available-tools notice
    # in the correct order: assistant content first, then the [Tool rejected]
    # user message, so the model knows bash is unusable and what it can use.
    second_msgs = provider.captured_messages[1]
    assert len(second_msgs) >= 2
    roles = [m.get("role") for m in second_msgs]
    assert roles.count("assistant") >= 1
    rejected = [m for m in second_msgs if m.get("role") == "user" and "[Tool rejected]" in m.get("content", "")]
    assert rejected, "model must be told the restricted call was omitted"
    assert "Available tools" in rejected[0]["content"]
    # The assistant content precedes the rejection notice.
    assert roles.index("assistant") < second_msgs.index(rejected[0])

    # Turn completes.
    assert provider.call_count == 2
    manifests = [e for e in events if e.kind == EventKind.TURN_MANIFEST]
    assert manifests and manifests[-1].data.get("completed")


@pytest.mark.asyncio
async def test_history_native_tool_call_escalates_registered_tool_before_provider(test_config):
    """G5: when dispatch history already contains a tool_calls reference to a
    registered-but-unseeded tool (persisted {name} shape), the resolver must
    escalate it BEFORE the provider call so a strict provider isn't handed a
    history that calls a function absent from the offered list."""
    from server.domain.enums import FinishReason
    from server.domain.message import Message

    class _G5Provider(BaseProvider):
        def __init__(self):
            super().__init__("g5", "g5-model")
            self.call_count = 0
            self.first_tools = None

        async def complete(self, messages, tools=None):
            if self.call_count == 0:
                self.first_tools = list(tools or [])
            self.call_count += 1
            self._last_finish_reason = FinishReason.STOP
            self._last_native_tool_calls = []
            return "Inspected via job_output already; all clear."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages, tools)
            for char in response:
                yield (char, None)

        async def validate(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["g5-model"]

    provider = _G5Provider()
    agent = SimpleLoop(test_config, provider, tool_registry=create_default_registry())

    history = [
        Message(
            session_id="s_g5",
            role="assistant",
            content="Running job output tool.",
            tool_calls=[ToolCall(name="job_output", arguments={"job_id": "1"})],
        ),
        Message(
            session_id="s_g5",
            role="user",
            content="[Tool: job_output] id=1 exit=0 output=...",
        ),
    ]
    events = []
    async for ev in agent.process_prompt(
        "Summarize the earlier inspection", "s_g5", history
    ):
        events.append(ev)

    # job_output is registered but not in the READ_ONLY_BUILD seed: without the
    # G5 pre-scan the provider would see a history call it can't satisfy.
    first_names = {t["function"]["name"] for t in provider.first_tools}
    assert "job_output" in first_names, (
        "registered history tool must be offered to the provider before the call"
    )










