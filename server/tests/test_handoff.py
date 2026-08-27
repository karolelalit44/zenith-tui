"""Tests for the crafted hand-off (Phase 1 of the message-context-flow todo).

Verifies the design-spec invariants (§3.3 / §4.3):
  - assistant content is built from turn_manifest + last emitted text,
  - no placeholder / `[Cancelled by user]` is persisted when real work happened,
  - long working turns fall back to ConversationSummarizer,
  - empty/no-work turns persist the cancellation placeholder.
"""

from __future__ import annotations

import pytest

from server.agents.prompt_executor import (
    _build_crafted_handoff,
    _did_work,
    _turn_manifest_from_events,
)
from server.domain.events import Event, EventKind


def _manifest(**overrides) -> dict:
    payload = {
        "created": ["a.py"],
        "modified": [],
        "remaining": [],
        "completed": True,
        "stalled": False,
        "verified": True,
        "checks": [],
    }
    payload.update(overrides)
    return payload


def _manifest_event(manifest: dict) -> Event:
    return Event(kind=EventKind.TURN_MANIFEST, data={"manifest": manifest})


class TestHelpers:
    def test_build_crafted_handoff_includes_header_and_body(self):
        handoff = _build_crafted_handoff(_manifest(), "Fixed the bug and verified.")
        assert "Created: a.py" in handoff
        assert "Verified: true" in handoff
        assert "Fixed the bug and verified." in handoff

    def test_build_crafted_handoff_modified_and_remaining(self):
        m = _manifest(
            created=[],
            modified=["b.py", "c.py"],
            verified=False,
            remaining=["Need a follow-up."],
        )
        handoff = _build_crafted_handoff(m, "")
        assert "Modified: b.py, c.py" in handoff
        assert "Verified: false" in handoff
        assert "Need a follow-up." in handoff

    def test_build_crafted_handoff_body_only_when_no_manifest(self):
        assert _build_crafted_handoff(None, "Plain answer") == "Plain answer"
        assert _build_crafted_handoff(None, "") is None

    def test_turn_manifest_from_events_picks_last(self):
        events = [
            _manifest_event(_manifest(created=["first.py"])),
            _manifest_event(_manifest(created=["second.py"])),
            Event(kind=EventKind.SUCCESS, data={"message": "ok"}),
        ]
        m = _turn_manifest_from_events(events)
        assert m is not None
        assert m["created"] == ["second.py"]

    def test_did_work(self):
        assert _did_work(_manifest()) is True
        assert _did_work(_manifest(created=[], modified=["x.py"])) is True
        assert _did_work(_manifest(created=[], modified=[])) is False
        assert _did_work(None) is False


class _FakeMessageRepo:
    def __init__(self) -> None:
        self.created: list = []

    async def create(self, message) -> None:
        self.created.append(message)


class _Stub:
    """Minimal stand-in for PromptExecutor exposing only the three attributes used."""

    def __init__(self, repo, config, provider=None):
        self._message_repo = repo
        self._config = config
        self._provider = provider


@pytest.fixture
def config():
    from server.config.settings import AppSettings

    return AppSettings(home_dir="/tmp/handoff_test.db", workspace_root="/tmp")


class TestPersistAssistantMessage:
    async def _persist(self, stub, response_text, events, terminal_status="completed"):
        import types

        from server.agents.prompt_executor import PromptExecutor

        stub._summarize_handoff = types.MethodType(PromptExecutor._summarize_handoff, stub)
        await PromptExecutor._persist_assistant_message(
            stub, "s1", response_text, events, terminal_status=terminal_status
        )

    async def test_worked_turn_never_persists_placeholder(self, config):
        repo = _FakeMessageRepo()
        stub = _Stub(repo, config)
        manifest = _manifest(created=["a.py"], modified=["b.py"], verified=True)
        await self._persist(stub, "Done.", [_manifest_event(manifest)])
        assert len(repo.created) == 1
        content = repo.created[0].content
        assert "Created: a.py" in content
        assert "Modified: b.py" in content
        assert "Verified: true" in content
        assert "[Cancelled by user]" not in content

    async def test_worked_turn_with_no_text_still_non_empty(self, config):
        repo = _FakeMessageRepo()
        stub = _Stub(repo, config)
        manifest = _manifest(created=["only.py"], verified=False)
        await self._persist(stub, "", [_manifest_event(manifest)])
        assert len(repo.created) == 1
        assert "[Cancelled by user]" not in repo.created[0].content
        assert "Created: only.py" in repo.created[0].content

    async def test_no_work_persists_no_summary_placeholder(self, config):
        repo = _FakeMessageRepo()
        stub = _Stub(repo, config)
        manifest = _manifest(created=[], modified=[], verified=True)
        await self._persist(stub, "", [_manifest_event(manifest)])
        assert len(repo.created) == 1
        # Completed turns with no work and no text get the neutral placeholder;
        # "[Cancelled by user]" is reserved for real cancellations (P1.4).
        assert repo.created[0].content == "[No summary recorded]"

    async def test_cancelled_turn_persists_cancellation_placeholder(self, config):
        repo = _FakeMessageRepo()
        stub = _Stub(repo, config)
        manifest = _manifest(created=[], modified=[], verified=True)
        await self._persist(stub, "", [_manifest_event(manifest)], terminal_status="cancelled")
        assert len(repo.created) == 1
        assert repo.created[0].content == "[Cancelled by user]"

    async def test_errored_turn_persists_error_placeholder(self, config):
        repo = _FakeMessageRepo()
        stub = _Stub(repo, config)
        manifest = _manifest(created=[], modified=[], verified=True)
        await self._persist(stub, "", [_manifest_event(manifest)], terminal_status="error")
        assert len(repo.created) == 1
        assert repo.created[0].content == "[Turn ended with an error]"

    async def test_empty_events_and_text_skipped(self, config):
        repo = _FakeMessageRepo()
        stub = _Stub(repo, config)
        await self._persist(stub, "", [])
        assert repo.created == []

    async def test_long_worked_turn_falls_back_to_summarizer(self, config):
        class SummarizingProvider:
            model = "test-model"

            async def complete(self, messages, **kwargs):
                return "COMPACT SUMMARY OF THE LONG TURN"

        repo = _FakeMessageRepo()
        stub = _Stub(repo, config, provider=SummarizingProvider())
        manifest = _manifest(created=["big.py"], verified=True)
        long_text = "Repeated detail. " * 300  # > _HANDOFF_SUMMARY_CHARS
        events = [
            _manifest_event(manifest),
            Event(kind=EventKind.MESSAGE, data={"text": long_text}),
        ]
        await self._persist(stub, long_text, events)
        assert len(repo.created) == 1
        content = repo.created[0].content
        assert "Created: big.py" in content
        assert "COMPACT SUMMARY OF THE LONG TURN" in content

    async def test_property_worked_never_placeholder(self, config):
        """Property: any turn with created/modified != [] never stores the placeholder."""
        repo = _FakeMessageRepo()
        stub = _Stub(repo, config)
        for manifest in (
            _manifest(created=["x.py"]),
            _manifest(created=[], modified=["y.py"]),
            _manifest(created=["a.py"], modified=["b.py"], verified=False),
        ):
            await self._persist(stub, "something", [_manifest_event(manifest)])
        assert repo.created
        for msg in repo.created:
            assert "[Cancelled by user]" not in msg.content
            assert msg.content.strip()
