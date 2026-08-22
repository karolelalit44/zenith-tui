"""Regression tests for the hardening fixes (C-F07, C-F15, C-F24)."""

import asyncio
import sqlite3
from pathlib import Path

import pytest

import server.agents.session_workspace as sw
from server.domain.errors import MigrationError
from server.persistence.migrations import runner as migration_runner
from server.persistence.repositories import MessageRepository, SessionRepository
from server.persistence.connection import Database
from server.sessions.export import SessionExporter
from server.sessions.import_service import SessionImporter


@pytest.fixture
def test_config(temp_dir):
    from server.config.settings import AppSettings

    return AppSettings(db_path=str(temp_dir / "hw.db"), workspace_root=str(temp_dir))


@pytest.fixture
async def db(test_config):
    database = Database(test_config.db_path)
    await database.connect()
    yield database
    await database.close()


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
async def test_jsonl_reimport_does_not_duplicate_messages(db, temp_dir):
    srepo = SessionRepository(db)
    mrepo = MessageRepository(db)

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

    # Import into a clean database, then re-import into the same one.
    clean_db = Database(str(temp_dir / "clean.db"))
    await clean_db.connect()
    try:
        clean_srepo = SessionRepository(clean_db)
        clean_mrepo = MessageRepository(clean_db)
        importer = SessionImporter(clean_srepo, clean_mrepo)
        first_session, first_imported = await importer.import_from_jsonl(export_path)
        assert len(first_imported) == 3

        _, second_imported = await importer.import_from_jsonl(export_path)
        assert second_imported == [], (
            f"re-import duplicated {len(second_imported)} messages instead of deduping"
        )
        reloaded = await clean_mrepo.get_by_session(first_session.id)
        assert len(reloaded) == 3
    finally:
        await clean_db.close()


# --------------------------------------------------------------------------
# C-F24: a failing migration must roll back DDL and leave no tracking stamp.
# --------------------------------------------------------------------------


def test_failed_migration_rolls_back_atomically(temp_dir):
    db_path = str(temp_dir / "atomic.db")
    migration_runner.ensure_tracking_table(db_path)

    bad_sql = Path(temp_dir) / "901_bad_migration.sql"
    bad_sql.write_text(
        "-- atomicity probe\n"
        "CREATE TABLE atomic_probe (id INTEGER PRIMARY KEY);\n"
        "INSERT INTO atomic_probe VALUES (1);\n"
        "THIS IS NOT VALID SQL;\n",
        encoding="utf-8",
    )
    migration = {
        "version": "901",
        "title": "bad migration",
        "filename": bad_sql.name,
        "path": bad_sql,
    }
    with pytest.raises((MigrationError, sqlite3.Error)):
        migration_runner._apply_file(db_path, migration)

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        stamps = [r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()]
    finally:
        conn.close()
    assert "atomic_probe" not in tables, "failed migration left DDL behind (no rollback)"
    assert "901" not in stamps, "failed migration left a tracking stamp behind"

    # The database remains usable and a good migration still applies.
    good_sql = Path(temp_dir) / "902_good_migration.sql"
    good_sql.write_text(
        "CREATE TABLE good_probe (id INTEGER PRIMARY KEY);\n", encoding="utf-8"
    )
    migration_runner._apply_file(
        db_path,
        {"version": "902", "title": "good", "filename": good_sql.name, "path": good_sql},
    )
    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        stamps = [r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()]
    finally:
        conn.close()
    assert "good_probe" in tables and "902" in stamps
