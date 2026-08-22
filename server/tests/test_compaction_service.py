"""Focused tests for the canonical CompactionService (automatic + manual)."""

import asyncio
import datetime

import pytest

from server.agents.compaction_service import (
    CompactionService,
    CompactionStatus,
    CompactionTrigger,
    _generations,
    generation_for,
)
from server.config.constants import DEFAULT_CONTEXT_WINDOW
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.domain.message import Message
from server.domain.session import Session
from server.persistence.connection import Database
from server.providers.base import BaseProvider


class StubProvider(BaseProvider):
    def __init__(self, total_tokens: int = 0, context_window: int = DEFAULT_CONTEXT_WINDOW):
        super().__init__("test", "test-model")
        self._context_window = context_window

    async def complete(self, messages: list[dict], tools=None) -> str:
        return "summarized"

    async def stream(
        self, messages: list[dict], tools=None, tool_choice=None, response_format=None
    ):
        for char in "summarized":
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["test-model"]


@pytest.fixture
def test_config(temp_dir):
    return AppSettings(
        providers={"test": ProviderConfig(model="test-model", is_active=True)},
        active_provider="test",
        db_path=str(temp_dir / "test.db"),
        workspace_root=str(temp_dir),
    )


@pytest.fixture
async def db(test_config):
    d = Database(test_config.db_path)
    await d.connect()
    yield d
    await d.close()


@pytest.fixture
async def service(db, test_config):
    from server.persistence.repositories import MessageRepository, SessionRepository

    provider = StubProvider()
    session_repo = SessionRepository(db)
    message_repo = MessageRepository(db)
    svc = CompactionService(
        test_config, provider, session_repo=session_repo, message_repo=message_repo
    )
    return (svc, session_repo, message_repo)


async def _seed_turns(message_repo, session_id, turns=5, filler=40000):
    """Seed turn pairs with explicit timestamps so history ordering is deterministic."""
    base = datetime.datetime(2026, 1, 1, 12, 0, 0)
    for i in range(turns):
        await message_repo.create(
            Message(
                session_id=session_id,
                role="user",
                content=f"User prompt {i} " + "x" * filler,
                created_at=base + datetime.timedelta(milliseconds=2 * i),
            )
        )
        await message_repo.create(
            Message(
                session_id=session_id,
                role="assistant",
                content=f"Assistant response {i}",
                created_at=base + datetime.timedelta(milliseconds=2 * i + 1),
            )
        )


@pytest.mark.asyncio
async def test_automatic_compaction_truncates_prefix_and_persists(db, service, test_config):
    svc, session_repo, message_repo = service
    session = await session_repo.create(Session(title="Auto Compact"))
    await _seed_turns(message_repo, session.id)
    events = []

    async def emit(ev):
        events.append(ev)

    history = await message_repo.get_by_session(session.id)
    outcome = await svc.compact(
        session_id=session.id,
        history=history,
        trigger=CompactionTrigger.AUTOMATIC,
        reason="automatic",
        emit=emit,
    )
    assert outcome.status == CompactionStatus.COMPLETED
    assert outcome.trigger == CompactionTrigger.AUTOMATIC
    assert outcome.summary == "summarized"
    assert outcome.cut > 0
    assert outcome.kept_tail > 0
    assert outcome.tokens_saved > 0
    assert outcome.deleted == outcome.cut
    loaded = await message_repo.get_by_session(session.id)
    assert len(loaded) == outcome.kept_tail
    assert loaded[-1].content == "Assistant response 4"
    updated = await session_repo.get(session.id)
    assert (updated.metadata or {}).get("summary") == "summarized"
    started = [e for e in events if e.kind == EventKind.CONTEXT_COMPACTION_STARTED]
    ended = [e for e in events if e.kind == EventKind.CONTEXT_COMPACTION_ENDED]
    assert started and started[-1].data.get("trigger") == "automatic"
    assert ended and ended[-1].data.get("status") == "completed"
    assert ended[-1].data.get("trigger") == "automatic"
    assert not ended[-1].data.get("failed")
    assert ended[-1].data.get("tokensSaved", 0) > 0


@pytest.mark.asyncio
async def test_manual_compaction_is_identical_operation_with_manual_trigger(
    db, service, test_config
):
    svc, session_repo, message_repo = service
    session = await session_repo.create(Session(title="Manual Compact"))
    await _seed_turns(message_repo, session.id)
    events = []

    async def emit(ev):
        events.append(ev)

    history = await message_repo.get_by_session(session.id)
    outcome = await svc.compact(
        session_id=session.id,
        history=history,
        trigger=CompactionTrigger.MANUAL,
        reason="manual",
        emit=emit,
    )
    assert outcome.status == CompactionStatus.COMPLETED
    assert outcome.trigger == CompactionTrigger.MANUAL
    assert outcome.summary == "summarized"
    assert outcome.cut > 0
    loaded = await message_repo.get_by_session(session.id)
    assert 0 < len(loaded) < 10
    ended = [e for e in events if e.kind == EventKind.CONTEXT_COMPACTION_ENDED]
    assert ended and ended[-1].data.get("trigger") == "manual"


@pytest.mark.asyncio
async def test_concurrent_compaction_skips_without_events(db, service, test_config):
    svc, session_repo, message_repo = service
    session = await session_repo.create(Session(title="Concurrent"))
    await _seed_turns(message_repo, session.id)
    events = []

    async def emit(ev):
        events.append(ev)

    history = await message_repo.get_by_session(session.id)
    first, second = await asyncio.gather(
        svc.compact(session_id=session.id, history=history, emit=emit),
        svc.compact(session_id=session.id, history=history, emit=emit),
    )
    assert first.status == CompactionStatus.COMPLETED
    assert second.status == CompactionStatus.SKIPPED
    assert second.trigger == CompactionTrigger.AUTOMATIC
    # The skipped run emitted nothing: exactly one started + one ended total.
    assert sum(1 for e in events if e.kind == EventKind.CONTEXT_COMPACTION_STARTED) == 1
    assert sum(1 for e in events if e.kind == EventKind.CONTEXT_COMPACTION_ENDED) == 1
    assert second.generation == generation_for(session.id)


@pytest.mark.asyncio
async def test_summarize_failure_mutates_nothing(db, service, test_config, monkeypatch):
    svc, session_repo, message_repo = service
    session = await session_repo.create(Session(title="Failure"))
    await _seed_turns(message_repo, session.id)
    events = []

    async def emit(ev):
        events.append(ev)

    class Boom(Exception):
        pass

    from server.agents import compaction_service

    async def broken(self, *a, **k):
        raise Boom("summarizer down")

    monkeypatch.setattr(compaction_service.ConversationSummarizer, "summarize", broken)
    history = await message_repo.get_by_session(session.id)
    outcome = await svc.compact(
        session_id=session.id,
        history=history,
        trigger=CompactionTrigger.MANUAL,
        reason="manual",
        emit=emit,
    )
    assert outcome.status == CompactionStatus.FAILED
    assert outcome.failed
    assert "summarizer down" in (outcome.error or "")
    loaded = await message_repo.get_by_session(session.id)
    assert len(loaded) == 10
    updated = await session_repo.get(session.id)
    assert not (updated.metadata or {}).get("summary")
    ended = [e for e in events if e.kind == EventKind.CONTEXT_COMPACTION_ENDED]
    assert ended and ended[-1].data.get("failed") is True
    assert ended[-1].data.get("status") == "failed"


@pytest.mark.asyncio
async def test_empty_summary_is_a_failure(db, service, test_config, monkeypatch):
    svc, session_repo, message_repo = service
    session = await session_repo.create(Session(title="Empty Summary"))
    await _seed_turns(message_repo, session.id)

    from server.agents import compaction_service

    async def empty(self, *a, **k):
        return ""

    monkeypatch.setattr(compaction_service.ConversationSummarizer, "summarize", empty)
    history = await message_repo.get_by_session(session.id)
    outcome = await svc.compact(
        session_id=session.id,
        history=history,
        trigger=CompactionTrigger.AUTOMATIC,
        emit=lambda ev: asyncio.sleep(0),
    )
    assert outcome.status == CompactionStatus.FAILED
    loaded = await message_repo.get_by_session(session.id)
    assert len(loaded) == 10
    updated = await session_repo.get(session.id)
    assert not (updated.metadata or {}).get("summary")


@pytest.mark.asyncio
async def test_stale_generation_never_persists(db, service, test_config, monkeypatch):
    svc, session_repo, message_repo = service
    session = await session_repo.create(Session(title="Stale"))
    await _seed_turns(message_repo, session.id)

    from server.agents import compaction_service

    original = compaction_service.ConversationSummarizer.summarize

    async def superseding(self, *a, **k):
        # A newer compaction starts and completes while this one is summarizing.
        _generations[session.id] += 1
        return await original(self, *a, **k)

    monkeypatch.setattr(compaction_service.ConversationSummarizer, "summarize", superseding)
    history = await message_repo.get_by_session(session.id)
    outcome = await svc.compact(
        session_id=session.id,
        history=history,
        trigger=CompactionTrigger.AUTOMATIC,
        emit=lambda ev: asyncio.sleep(0),
    )
    assert outcome.status == CompactionStatus.COMPLETED
    assert outcome.deleted == 0
    loaded = await message_repo.get_by_session(session.id)
    assert len(loaded) == 10
    updated = await session_repo.get(session.id)
    assert not (updated.metadata or {}).get("summary")


@pytest.mark.asyncio
async def test_restart_resume_uses_compacted_state(db, service, test_config):
    svc, session_repo, message_repo = service
    session = await session_repo.create(Session(title="Restart"))
    await _seed_turns(message_repo, session.id)
    history = await message_repo.get_by_session(session.id)
    outcome = await svc.compact(
        session_id=session.id,
        history=history,
        trigger=CompactionTrigger.MANUAL,
        reason="manual",
        emit=lambda ev: asyncio.sleep(0),
    )
    assert outcome.status == CompactionStatus.COMPLETED

    # Simulate a restart: a fresh service instance over the same repositories.
    fresh = CompactionService(
        test_config, StubProvider(), session_repo=session_repo, message_repo=message_repo
    )
    loaded = await message_repo.get_by_session(session.id)
    assert len(loaded) == outcome.kept_tail
    session2 = await session_repo.get(session.id)
    summary = (session2.metadata or {}).get("summary")
    assert summary == "summarized"
    second = await fresh.compact(
        session_id=session.id,
        history=loaded,
        trigger=CompactionTrigger.MANUAL,
        reason="manual",
        previous_summary=summary,
        emit=lambda ev: asyncio.sleep(0),
    )
    # The truncated history already fits the budget: nothing summarizable,
    # so the service must report a skip (never fabricate a summary, never
    # truncate, and never let the caller rebuild context from an empty tail).
    assert second.status == CompactionStatus.SKIPPED
    assert second.cut == 0
    assert second.deleted == 0


@pytest.mark.asyncio
async def test_persistence_failure_marks_outcome_failed(db, service, test_config, monkeypatch):
    """C-F04: if the durable persist step fails, the outcome is FAILED."""
    svc, session_repo, message_repo = service
    session = await session_repo.create(Session(title="PersistFail"))
    await _seed_turns(message_repo, session.id)

    async def boom(session_id, metadata, delete_ids):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(message_repo, "compact_history", boom)
    events = []

    async def emit(ev):
        events.append(ev)

    history = await message_repo.get_by_session(session.id)
    outcome = await svc.compact(
        session_id=session.id,
        history=history,
        trigger=CompactionTrigger.MANUAL,
        reason="manual",
        emit=emit,
    )
    assert outcome.status == CompactionStatus.FAILED
    assert "disk on fire" in (outcome.error or "")
    ended = [e for e in events if e.kind == EventKind.CONTEXT_COMPACTION_ENDED]
    assert ended and ended[-1].data.get("status") == "failed"
    # Nothing was persisted.
    loaded = await message_repo.get_by_session(session.id)
    assert len(loaded) == len(history)
    updated = await session_repo.get(session.id)
    assert not (updated.metadata or {}).get("summary")


@pytest.mark.asyncio
async def test_post_persist_emit_failure_stays_completed_with_warnings(
    db, service, test_config, monkeypatch
):
    """C-F04: failures after the durable boundary warn but keep COMPLETED."""
    svc, session_repo, message_repo = service
    session = await session_repo.create(Session(title="EmitFail"))
    await _seed_turns(message_repo, session.id)

    real_compact_history = message_repo.compact_history

    async def compact_then_bump(session_id, metadata, delete_ids):
        deleted = await real_compact_history(session_id, metadata, delete_ids)
        # A newer compaction generation starts before the apply step runs.
        import server.agents.compaction_service as cs

        cs._generations[session_id] = cs._generations.get(session_id, 0) + 1
        return deleted

    monkeypatch.setattr(message_repo, "compact_history", compact_then_bump)
    live_messages = [{"role": "user", "content": f"turn {i}"} for i in range(6)]
    outcome = await svc.compact(
        session_id=session.id,
        history=await message_repo.get_by_session(session.id),
        messages=live_messages,
        trigger=CompactionTrigger.MANUAL,
        reason="manual",
        emit=lambda ev: asyncio.sleep(0),
    )
    # Durable state committed -> COMPLETED with a warning about the skipped apply.
    assert outcome.status == CompactionStatus.COMPLETED
    assert outcome.has_warnings
    assert any("generation advanced" in w for w in outcome.warnings)
    # The in-memory list was left untouched because its generation is stale.
    assert len(live_messages) == 6
    loaded = await message_repo.get_by_session(session.id)
    assert len(loaded) == outcome.kept_tail
    updated = await session_repo.get(session.id)
    assert (updated.metadata or {}).get("summary") == "summarized"


@pytest.mark.asyncio
async def test_end_event_delivery_failure_recorded_as_warning(db, service, test_config, monkeypatch):
    """A raising emit for the end event must not fail the compaction."""
    from server.domain.events import EventKind as EK

    svc, session_repo, message_repo = service
    session = await session_repo.create(Session(title="EndEmitFail"))
    await _seed_turns(message_repo, session.id)

    async def emit(ev):
        if ev.kind == EK.CONTEXT_COMPACTION_ENDED:
            raise RuntimeError("socket gone")
        # started/phase events swallowed

    outcome = await svc.compact(
        session_id=session.id,
        history=await message_repo.get_by_session(session.id),
        trigger=CompactionTrigger.MANUAL,
        reason="manual",
        emit=emit,
    )
    assert outcome.status == CompactionStatus.COMPLETED
    assert outcome.has_warnings
    assert any("end-event delivery failed" in w for w in outcome.warnings)
    loaded = await message_repo.get_by_session(session.id)
    assert len(loaded) == outcome.kept_tail
