"""Answer-completion semantics (AGENT_RELIABILITY_PLAN P0/P1).

Regression tests for the turn-9 failure class: an informational request whose
answer was fully delivered yet finalized as ``stalled`` with fabricated state.

Contract under test:
- AC-1: substantive answer + only-duplicate tool calls => clean completion
  (``completed=True``, never ``stall_finalized``) when nothing is pending.
- AC-2: an answer-only turn reports ``answered=True`` and an honest empty
  ``remaining`` list.
- AC-3: a genuine stall must not fabricate a placeholder "remaining" item;
  the list stays empty when structured state has no pending work.
"""

import pytest

from server.agents.loop import AgentLoop
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.providers.base import BaseProvider
from server.toolkit import create_default_registry

_ANSWER = (
    "The app has four major features: terminal chat UI, agent loop with tools, "
    "provider management, and session persistence."
)
_READ_CALL = '```tool\n{"tool": "file_read", "params": {"path": "notes.txt"}}\n```'


class _AnswerPlusDuplicateProvider(BaseProvider):
    """Turn-9 repro: explores once, stalls once, then answers with a stray dup."""

    def __init__(self):
        super().__init__("ansdup", "ansdup-model")
        self.call_count = 0

    async def complete(self, messages, tools=None):
        self.call_count += 1
        if self.call_count == 1:
            return _READ_CALL
        if self.call_count == 2:
            # Duplicate-only pass, no text -> legitimate stall warning.
            return _READ_CALL
        # Final answer delivered WITH a stray duplicate call (the defect).
        return _ANSWER + "\n" + _READ_CALL

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        response = await self.complete(messages, tools)
        for char in response:
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["ansdup-model"]


class _AnswerOnlyProvider(BaseProvider):
    """Answers in prose immediately; never emits a tool call."""

    def __init__(self):
        super().__init__("ansonly", "ansonly-model")

    async def complete(self, messages, tools=None):
        return _ANSWER

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        response = await self.complete(messages, tools)
        for char in response:
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["ansonly-model"]


class _GenuineStallProvider(BaseProvider):
    """Executes one read then repeats it forever with only short chatter."""

    def __init__(self):
        super().__init__("stalled", "stalled-model")
        self.call_count = 0

    async def complete(self, messages, tools=None):
        self.call_count += 1
        if self.call_count == 1:
            return _READ_CALL
        # Short chatter + the same call again: genuine stuck-loop behavior.
        return "Working on it.\n" + _READ_CALL

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        response = await self.complete(messages, tools)
        for char in response:
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["stalled-model"]


@pytest.fixture
def test_config(temp_dir):
    return AppSettings(
        providers={"test": ProviderConfig(model="test-model", is_active=True)},
        active_provider="test",
        home_dir=str(temp_dir / "test.db"),
        workspace_root=str(temp_dir),
    )


def _manifests(events):
    return [e.data for e in events if e.kind == EventKind.TURN_MANIFEST]


@pytest.mark.asyncio
async def test_answer_with_stray_duplicate_call_completes_cleanly(test_config, temp_dir):
    """AC-1: a delivered answer plus duplicate-only calls must NOT stall the turn."""
    (temp_dir / "notes.txt").write_text("notes", encoding="utf-8")
    provider = _AnswerPlusDuplicateProvider()
    agent = AgentLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt(
        "Summarize the major features of this app in brief", "s1", [], "build"
    ):
        events.append(event)

    assert events[-1].kind == EventKind.SUCCESS, f"final event: {events[-1]}"
    manifests = _manifests(events)
    assert manifests, "turn must emit a manifest"
    manifest = manifests[-1]
    assert manifest.get("completed") is True, f"manifest: {manifest}"
    assert manifest.get("stalled") is False, f"manifest: {manifest}"
    assert manifest.get("remaining") == [], f"manifest: {manifest}"
    assert manifest.get("answered") is True, f"manifest: {manifest}"
    # The answer itself reached the user exactly once.
    answers = [
        e.data.get("text")
        for e in events
        if e.kind == EventKind.MESSAGE and (e.data.get("text") or "").startswith("The app has four")
    ]
    assert len(answers) == 1, f"answer emitted {len(answers)} times"


@pytest.mark.asyncio
async def test_answer_only_turn_manifest_is_honest(test_config):
    """AC-2: prose-only turns complete with answered=True and empty remaining."""
    provider = _AnswerOnlyProvider()
    agent = AgentLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("What are the major features?", "s1", [], "build"):
        events.append(event)

    assert events[-1].kind == EventKind.SUCCESS
    manifests = _manifests(events)
    assert manifests
    manifest = manifests[-1]
    assert manifest.get("completed") is True, f"manifest: {manifest}"
    assert manifest.get("stalled") is False, f"manifest: {manifest}"
    assert manifest.get("remaining") == [], f"manifest: {manifest}"
    assert manifest.get("answered") is True, f"manifest: {manifest}"


@pytest.mark.asyncio
async def test_genuine_stall_does_not_fabricate_remaining(test_config, temp_dir):
    """AC-3: a real stall reports stalled honestly, without placeholder items."""
    (temp_dir / "notes.txt").write_text("notes", encoding="utf-8")
    provider = _GenuineStallProvider()
    agent = AgentLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Do the work", "s1", [], "build"):
        events.append(event)

    manifests = _manifests(events)
    assert manifests
    manifest = manifests[-1]
    assert manifest.get("stalled") is True, f"manifest: {manifest}"
    assert manifest.get("completed") is False, f"manifest: {manifest}"
    assert manifest.get("remaining") == [], (
        "genuine stall with no pending work must leave remaining empty; "
        f"got: {manifest.get('remaining')}"
    )
