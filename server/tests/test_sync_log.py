from __future__ import annotations

import pytest

from server.api.websocket import ConnectionManager
from server.persistence.repositories import (
    CheckpointRepository,
    DraftRepository,
    MessageRepository,
    SessionRepository,
    SessionStatusHistoryRepository,
    SyncEventRepository,
    TokenUsageRepository,
)
from server.providers.responder import error, message_event, thinking, tool_call, tool_result
from server.sessions.service import DefaultSessionService


@pytest.fixture
async def session_service(db):
    svc = DefaultSessionService(
        session_repo=SessionRepository(db),
        message_repo=MessageRepository(db),
        token_usage_repo=TokenUsageRepository(db),
        checkpoint_repo=CheckpointRepository(db),
        sync_event_repo=SyncEventRepository(db),
        status_history_repo=SessionStatusHistoryRepository(db),
        draft_repo=DraftRepository(db),
    )
    return svc


async def make_session(svc, title="HP-2 Test") -> str:
    session = await svc.create(title=title)
    return session.id


class TestDurableEventLog:
    async def test_message_and_tool_events_persisted(self, session_service, db):
        sid = await make_session(session_service)
        manager = ConnectionManager()
        manager.set_session_service(session_service)
        await manager.register(sid, None)
        events = [
            thinking("processing...", sid),
            message_event("streaming chunk", sid, partial=True),
            message_event("Hello from assistant", sid, partial=False),
            tool_call("file_write", {"path": "a.txt", "content": "x"}, sid),
            tool_result("file_write", True, sid, output="ok"),
            error("boom", sid, code="TEST"),
        ]
        for evt in events:
            await manager.send_event(sid, evt)
        repo = SyncEventRepository(db)
        rows = await repo.get_since(sid, 0)
        kinds = [(r["event_type"], r["event_data"]) for r in rows]
        assert any((t == "message" and d.get("text") == "Hello from assistant" for t, d in kinds))
        assert any((t == "tool_call" and d.get("tool") == "file_write" for t, d in kinds))
        assert any((t == "tool_result" and d.get("tool") == "file_write" for t, d in kinds))
        assert any((t == "error" and d.get("message") == "boom" for t, d in kinds))
        assert not any((t == "thinking" for t, _ in kinds))
        assert not any((t == "message" and d.get("partial") for t, d in kinds))
        seqs = [r["sequence"] for r in rows]
        assert seqs == sorted(seqs)

    async def test_resume_since_sequence_replays_in_order(self, session_service, db):
        sid = await make_session(session_service)
        manager = ConnectionManager()
        manager.set_session_service(session_service)
        await manager.register(sid, None)
        for i in range(3):
            await manager.send_event(sid, message_event(f"msg {i}", sid))
            await manager.send_event(sid, tool_call("grep", {"q": str(i)}, sid))
        repo = SyncEventRepository(db)
        all_rows = await repo.get_since(sid, 0)
        assert len(all_rows) == 6
        after = await repo.get_since(sid, all_rows[2]["sequence"])
        assert [r["sequence"] for r in after] == [r["sequence"] for r in all_rows[3:]]

    async def test_sequences_survive_restart(self, session_service, db):
        sid = await make_session(session_service)
        mgr1 = ConnectionManager()
        mgr1.set_session_service(session_service)
        await mgr1.register(sid, None)
        await mgr1.send_event(sid, message_event("before restart", sid))
        repo = SyncEventRepository(db)
        before = await repo.get_latest_sequence(sid)
        assert before >= 1
        mgr2 = ConnectionManager()
        mgr2.set_session_service(session_service)
        await mgr2.register(sid, None)
        await mgr2.send_event(sid, message_event("after restart", sid))
        rows = await repo.get_since(sid, 0)
        assert len(rows) == 2
        assert rows[0]["sequence"] < rows[1]["sequence"]
        seqs = [r["sequence"] for r in rows]
        assert len(seqs) == len(set(seqs))

    async def test_persist_failure_does_not_break_stream(self, session_service, db):
        sid = await make_session(session_service)
        manager = ConnectionManager()

        class ExplodingService:
            async def get_latest_sync_sequence(self, session_id):
                return 0

            async def record_sync_event(self, session_id, event_type, event_data, sequence=None):
                raise RuntimeError("db down")

        manager.set_session_service(ExplodingService())
        await manager.register(sid, None)
        await manager.send_event(sid, message_event("still works", sid))
        await manager.send_event(sid, tool_call("grep", {"q": "x"}, sid))
