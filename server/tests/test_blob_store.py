from __future__ import annotations

import json
from pathlib import Path

import pytest

from server.domain.message import Message
from server.persistence.blob_store import BlobStore
from server.persistence.repositories import (
    CheckpointRepository,
    DraftRepository,
    MessageRepository,
    SessionRepository,
    SessionStatusHistoryRepository,
    SyncEventRepository,
    TokenUsageRepository,
)
from server.providers.responder import tool_result
from server.sessions.export import SessionExporter
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


async def make_session(svc, title="HP-5 Test") -> str:
    session = await svc.create(title=title)
    return session.id


def _big_lines(n: int = 50000) -> list[str]:
    return [f"out line {i:05d}" for i in range(n)]


class TestBlobStoreUnit:
    def test_string_roundtrip(self, temp_dir):
        store = BlobStore(temp_dir / "blobs")
        pointer = store.store("x" * 10000)
        assert pointer.startswith("@@zenith-blob:")
        assert store.load(pointer) == "x" * 10000

    def test_small_string_untouched(self, temp_dir):
        store = BlobStore(temp_dir / "blobs")
        assert store.load("hello") == "hello"

    def test_missing_blob_returns_placeholder(self, temp_dir):
        store = BlobStore(temp_dir / "blobs")
        assert store.load("@@zenith-blob:doesnotexist") == "[blob missing]"

    def test_pack_unpack_large_list(self, temp_dir):
        store = BlobStore(temp_dir / "blobs")
        lines = _big_lines()
        packed = store.pack({"metadata": {"output_lines": lines}})
        assert isinstance(packed["metadata"]["output_lines"], str)
        assert packed["metadata"]["output_lines"].startswith("@@zenith-lines:")
        restored = store.unpack(packed)
        assert restored["metadata"]["output_lines"] == lines

    def test_pack_unpack_large_string(self, temp_dir):
        store = BlobStore(temp_dir / "blobs")
        big = "A" * 20000
        packed = store.pack({"output": big})
        assert packed["output"].startswith("@@zenith-blob:")
        assert store.unpack(packed)["output"] == big

    def test_small_values_pass_through(self, temp_dir):
        store = BlobStore(temp_dir / "blobs")
        data = {"tool": "bash", "success": True, "output": "ok", "meta": {"x": [1, 2]}}
        assert store.unpack(store.pack(data)) == data


class TestSyncEventBlob:
    async def test_large_output_keeps_row_small_and_restores(self, session_service, db, temp_dir):
        sid = await make_session(session_service)
        repo = SyncEventRepository(db)
        await repo.record(
            sid,
            "tool_result",
            {
                "tool": "bash",
                "success": True,
                "output": "ok",
                "metadata": {"output_lines": _big_lines()},
            },
            sequence=1,
        )
        rows = await db.fetch_all("SELECT event_data FROM sync_events WHERE session_id = ?", (sid,))
        stored = rows[0]["event_data"]
        assert len(stored) < 2000
        parsed = json.loads(stored)
        assert parsed["metadata"]["output_lines"].startswith("@@zenith-lines:")
        blob_files = list((Path(db.db_path).parent / "blobs").glob("*.txt"))
        assert blob_files, "expected blob file on disk"
        since = await repo.get_since(sid, 0)
        assert len(since) == 1
        assert since[0]["event_data"]["metadata"]["output_lines"] == _big_lines()

    async def test_small_output_no_blob(self, session_service, db):
        sid = await make_session(session_service)
        repo = SyncEventRepository(db)
        await repo.record(sid, "message", {"text": "hello world"}, sequence=1)
        since = await repo.get_since(sid, 0)
        assert since[0]["event_data"]["text"] == "hello world"
        blob_files = list((Path(db.db_path).parent / "blobs").glob("*.txt"))
        assert not blob_files


class TestMessageBlob:
    async def test_events_json_stays_small_but_reads_full(self, session_service, db):
        sid = await make_session(session_service)
        event = tool_result("bash", True, sid, output="ok", metadata={"output_lines": _big_lines()})
        msg = Message(session_id=sid, role="assistant", content="ran a big command", events=[event])
        await MessageRepository(db).create(msg)
        row = await db.fetch_one("SELECT events_json FROM messages WHERE session_id = ?", (sid,))
        assert len(row["events_json"]) < 2000
        assert "@@zenith-lines:" in row["events_json"]
        messages = await MessageRepository(db).get_by_session(sid)
        restored = messages[0].events[0].data
        assert restored["metadata"]["output_lines"] == _big_lines()

    async def test_export_renders_full_content(self, session_service, db):
        sid = await make_session(session_service)
        event = tool_result("bash", True, sid, output="ok", metadata={"output_lines": _big_lines()})
        msg = Message(session_id=sid, role="assistant", content="ran a big command", events=[event])
        await MessageRepository(db).create(msg)
        session = await session_service.require(sid)
        messages = await MessageRepository(db).get_by_session(sid)
        markdown = SessionExporter().export_to_string(session, messages)
        assert "ran a big command" in markdown
        assert "bash" in markdown
        messages2 = await MessageRepository(db).get_by_session(sid)
        assert messages2[0].events[0].data["metadata"]["output_lines"][-1] == "out line 49999"
