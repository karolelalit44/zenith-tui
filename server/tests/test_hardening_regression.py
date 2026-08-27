"""Regression tests for the hardening fixes (C-F07, C-F15).

The migration-atomicity cases (C-F24) died with the database layer; the
file-storage equivalents (atomic write interruption) live in
test_storage_atomic.py.
"""

from __future__ import annotations

import asyncio

import pytest

import server.agents.session_workspace as sw
from server.sessions.export import SessionExporter
from server.sessions.import_service import SessionImporter
from server.storage import StorageHome, ensure_materialized
from server.storage.session_store import FileMessageRepository, FileSessionRepository

# --------------------------------------------------------------------------
# C-F07: a workspace mutation during upsert_batch must keep the dirty flag.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flush_keeps_dirty_flag_when_workspace_mutates_midflight():
    sid = "s-flush-race"
    sw.reset_session(sid)
    try:
        sw.record_write(sid, "a.txt", "hello")
        assert sid in sw.get_dirty_sessions()

        class RacingRepo:
            async def upsert_batch(self, session_id, batch):
                # Simulate a concurrent turn mutating the workspace while the
                # batch is in flight: bumps the dirty epoch past the snapshot.
                await asyncio.sleep(0)
                paths = [r["path"] for r in batch]
                assert paths == ["a.txt"]
                sw.record_write(session_id, "b.txt", "mutated mid-flight")

            async def delete_session(self, session_id):  # pragma: no cover
                pass

        await sw.flush_to_db(sid, RacingRepo())
        # The post-flush clean-up must NOT clear the flag: b.txt was never persisted.
        assert sid in sw.get_dirty_sessions()

        class QuietRepo:
            async def upsert_batch(self, session_id, batch):
                assert [r["path"] for r in batch] == ["a.txt", "b.txt"]

            async def delete_session(self, session_id):  # pragma: no cover
                pass

        await sw.flush_to_db(sid, QuietRepo())
        assert sid not in sw.get_dirty_sessions()
    finally:
        sw.reset_session(sid)


# --------------------------------------------------------------------------
# C-F15: importing the same JSONL twice must not duplicate messages.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jsonl_reimport_does_not_duplicate_messages(temp_dir):
    source_home = StorageHome(temp_dir / "src")
    ensure_materialized(source_home)
    srepo = FileSessionRepository(source_home)
    mrepo = FileMessageRepository(source_home)

    from server.domain.message import Message
    from server.domain.session import Session

    source_session = await srepo.create(Session(title="ExportSource"))
    msgs = []
    for i in range(3):
        m = await mrepo.create(
            Message(
                session_id=source_session.id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"msg {i}",
            )
        )
        msgs.append(m)

    exporter = SessionExporter()
    export_path = exporter.export_jsonl(source_session, msgs, output_dir=str(temp_dir))

    # Import into a clean storage home, then re-import into the same one.
    clean_home = StorageHome(temp_dir / "dst")
    ensure_materialized(clean_home)
    clean_srepo = FileSessionRepository(clean_home)
    clean_mrepo = FileMessageRepository(clean_home)
    importer = SessionImporter(clean_srepo, clean_mrepo)
    first_session, first_imported = await importer.import_from_jsonl(export_path)
    assert len(first_imported) == 3

    _, second_imported = await importer.import_from_jsonl(export_path)
    assert second_imported == [], (
        f"re-import duplicated {len(second_imported)} messages instead of deduping"
    )
    reloaded = await clean_mrepo.get_by_session(first_session.id)
    assert len(reloaded) == 3
