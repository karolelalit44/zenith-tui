"""Encryption at rest for session data (Gap #10).

With ``ZENITH_ENCRYPTION_KEY`` set, ``messages.content``/``metadata_json`` and
``sessions.metadata_json`` are Fernet-encrypted on disk and transparently
decrypted on read. Without a key the store stays plaintext (backward
compatible), and the key value never appears in logs.
"""

import sqlite3

import pytest

from server.config.settings import AppSettings
from server.domain.message import Message
from server.domain.session import Session
from server.persistence.connection import Database
from server.persistence.crypto import (
    ENCRYPTED_PREFIX,
    ENCRYPTION_KEY_ENV,
    decrypt_text,
    encrypt_text,
    encryption_enabled,
)
from server.persistence.repositories.sessions import MessageRepository, SessionRepository

TEST_KEY = "test-encryption-key-passphrase-123"


@pytest.fixture
def enc_cfg(temp_dir, monkeypatch):
    monkeypatch.setenv(ENCRYPTION_KEY_ENV, TEST_KEY)
    from server.persistence import crypto

    crypto._fernet.cache_clear()
    return AppSettings(
        db_path=str(temp_dir / "enc.db"),
        workspace_root=str(temp_dir),
    )


@pytest.fixture
def plain_cfg(temp_dir, monkeypatch):
    monkeypatch.delenv(ENCRYPTION_KEY_ENV, raising=False)
    from server.persistence import crypto

    crypto._fernet.cache_clear()
    return AppSettings(
        db_path=str(temp_dir / "plain.db"),
        workspace_root=str(temp_dir),
    )


async def _write_session_and_messages(db: Database, title: str = "Encrypted Session"):
    sessions = SessionRepository(db)
    messages = MessageRepository(db)
    session = await sessions.create(
        Session(title=title, metadata={"summary": "secret plan details"})
    )
    await messages.create(
        Message(
            session_id=session.id,
            role="user",
            content="prompt with private code",
            metadata={"tag": "secret-tag"},
        )
    )
    await messages.create(
        Message(session_id=session.id, role="assistant", content="reply with API key abc123")
    )
    return session


class TestEncryptionAtRest:
    async def _db(self, cfg) -> Database:
        db = Database(cfg.db_path)
        await db.connect()
        return db

    @pytest.mark.asyncio
    async def test_round_trip_with_key(self, enc_cfg):
        db = await self._db(enc_cfg)
        session = await _write_session_and_messages(db)
        sessions = SessionRepository(db)
        messages = MessageRepository(db)
        loaded = await sessions.get(session.id)
        assert (loaded.metadata or {}).get("summary") == "secret plan details"
        rows = await messages.get_by_session(session.id)
        contents = {m.content for m in rows}
        assert "prompt with private code" in contents
        assert "reply with API key abc123" in contents
        by_role = {m.role: m for m in rows}
        assert by_role["user"].metadata.get("tag") == "secret-tag"
        await db.close()

    @pytest.mark.asyncio
    async def test_db_content_is_encrypted_with_key(self, enc_cfg):
        db = await self._db(enc_cfg)
        await _write_session_and_messages(db)
        await db.close()
        conn = sqlite3.connect(enc_cfg.db_path)
        try:
            rows = conn.execute("SELECT content, metadata_json FROM messages").fetchall()
            assert rows
            for content, metadata in rows:
                assert content.startswith(ENCRYPTED_PREFIX)
                assert metadata.startswith(ENCRYPTED_PREFIX)
            sess = conn.execute("SELECT metadata_json FROM sessions").fetchone()
            assert sess[0].startswith(ENCRYPTED_PREFIX)
        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_plaintext_mode_without_key(self, plain_cfg):
        db = await self._db(plain_cfg)
        await _write_session_and_messages(db, "Plain Session")
        await db.close()
        conn = sqlite3.connect(plain_cfg.db_path)
        try:
            rows = conn.execute("SELECT content, metadata_json FROM messages").fetchall()
            assert rows
            for content, metadata in rows:
                assert not content.startswith(ENCRYPTED_PREFIX)
                assert not metadata.startswith(ENCRYPTED_PREFIX)
            sess = conn.execute("SELECT metadata_json FROM sessions").fetchone()
            assert not sess[0].startswith(ENCRYPTED_PREFIX)
            assert "secret plan details" in sess[0]
        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_plaintext_db_reads_without_key(self, plain_cfg):
        db = await self._db(plain_cfg)
        session = await _write_session_and_messages(db, "Plain Session")
        sessions = SessionRepository(db)
        messages = MessageRepository(db)
        loaded = await sessions.get(session.id)
        assert (loaded.metadata or {}).get("summary") == "secret plan details"
        rows = await messages.get_by_session(session.id)
        assert any(m.content == "prompt with private code" for m in rows)
        await db.close()

    @pytest.mark.asyncio
    async def test_key_never_appears_in_logs(self, enc_cfg, caplog):
        db = await self._db(enc_cfg)
        await _write_session_and_messages(db)
        await db.close()
        assert TEST_KEY not in caplog.text

    def test_helpers_noop_without_key(self, plain_cfg, monkeypatch):
        from server.persistence import crypto

        crypto._fernet.cache_clear()
        assert not encryption_enabled()
        assert encrypt_text("hello") == "hello"
        assert decrypt_text("hello") == "hello"
        crypto._fernet.cache_clear()

    def test_helpers_round_trip_with_key(self, enc_cfg):
        from server.persistence import crypto

        cipher = encrypt_text("top secret")
        assert cipher.startswith(ENCRYPTED_PREFIX)
        assert decrypt_text(cipher) == "top secret"
        assert decrypt_text("plain") == "plain"
        crypto._fernet.cache_clear()

    def test_encrypted_value_without_key_passes_through(self, plain_cfg, caplog):
        from server.persistence import crypto

        crypto._fernet.cache_clear()
        raw = ENCRYPTED_PREFIX + "garbage"
        assert decrypt_text(raw) == raw
        assert "ZENITH_ENCRYPTION_KEY is not set" in caplog.text
        crypto._fernet.cache_clear()