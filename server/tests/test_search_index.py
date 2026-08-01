"""Tests for HP-9 — FTS5 search index over sessions/messages + session.search."""

from __future__ import annotations

from datetime import datetime

import pytest

from server.domain.message import Message
from server.persistence.connection import Database
from server.persistence.repositories import MessageRepository, SessionRepository
from server.persistence.search import SearchRepository, _escape_query
from server.domain.session import Session


class TestEscapeQuery:
    def test_bare_phrase(self):
        assert _escape_query("auth token") == '"auth" "token"'

    def test_special_chars_quoted(self):
        assert _escape_query('say "hi" now') == '"say" "hi" "now"'

    def test_empty(self):
        assert _escape_query("") == ""
        assert _escape_query("   ") == ""


class TestSearchRepository:
    async def _setup(self, temp_dir):
        db = Database(str(temp_dir / "test.db"))
        await db.connect()
        session_repo = SessionRepository(db)
        msg_repo = MessageRepository(db)
        session = Session(
            id="s-auth",
            title="Auth token work",
            state="active",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        await session_repo.create(session)
        session2 = Session(
            id="s-other",
            title="Frontend styling",
            state="active",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        await session_repo.create(session2)
        await msg_repo.create(Message(
            session_id="s-auth",
            role="user",
            content="Please rotate the auth token every day.",
            token_count=10,
        ))
        await msg_repo.create(Message(
            session_id="s-auth",
            role="assistant",
            content="Done. The JWT auth token is now rotated daily.",
            token_count=12,
        ))
        await msg_repo.create(Message(
            session_id="s-other",
            role="user",
            content="Make the button blue please.",
            token_count=8,
        ))
        return db, session_repo, msg_repo

    @pytest.mark.asyncio
    async def test_search_messages_ranked(self, temp_dir):
        db, *_ = await self._setup(temp_dir)
        try:
            repo = SearchRepository(db)
            hits = await repo.search("auth token")
            msg_hits = [h for h in hits if h["type"] == "message"]
            assert len(msg_hits) >= 2
            for h in msg_hits:
                assert h["session_id"] == "s-auth"
                assert h["title"] == "Auth token work"
                assert "auth" in h["snippet"].lower() or "token" in h["snippet"].lower()
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_search_sessions_by_title(self, temp_dir):
        db, *_ = await self._setup(temp_dir)
        try:
            repo = SearchRepository(db)
            hits = await repo.search("styling")
            sess_hits = [h for h in hits if h["type"] == "session"]
            assert any(h["session_id"] == "s-other" for h in sess_hits)
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_search_scoped_to_session(self, temp_dir):
        db, *_ = await self._setup(temp_dir)
        try:
            repo = SearchRepository(db)
            hits = await repo.search("token", session_id="s-other")
            assert all(h["session_id"] == "s-other" for h in hits)
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_empty_query_returns_nothing(self, temp_dir):
        db, *_ = await self._setup(temp_dir)
        try:
            repo = SearchRepository(db)
            assert await repo.search("") == []
            assert await repo.search("   ") == []
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_index_parity_with_messages(self, temp_dir):
        db, *_ = await self._setup(temp_dir)
        try:
            repo = SearchRepository(db)
            parity = await repo.index_parity()
            assert parity["messages"] == parity["message_fts"] == 3
            assert parity["sessions"] == parity["session_fts"] == 2
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_triggers_keep_index_in_sync(self, temp_dir):
        db, session_repo, msg_repo = await self._setup(temp_dir)
        try:
            # Insert a new message → index updates via trigger
            await msg_repo.create(Message(
                session_id="s-other",
                role="assistant",
                content="The palette uses auth-themed accent colors.",
                token_count=9,
            ))
            repo = SearchRepository(db)
            parity = await repo.index_parity()
            assert parity["messages"] == parity["message_fts"] == 4
            hits = await repo.search("palette")
            assert any("palette" in h["snippet"].lower() for h in hits)
        finally:
            await db.close()


class TestSessionSearchRPC:
    @pytest.mark.asyncio
    async def test_search_handler_returns_hits(self, temp_dir):
        from server.api.handlers import MethodHandlers
        db = Database(str(temp_dir / "test.db"))
        await db.connect()
        try:
            from server.persistence.repositories import MessageRepository, SessionRepository
            session_repo = SessionRepository(db)
            msg_repo = MessageRepository(db)
            session = Session(
                id="s1", title="Auth token work",
                state="active",
                created_at=datetime.now(), updated_at=datetime.now(),
            )
            await session_repo.create(session)
            await msg_repo.create(Message(
                session_id="s1", role="user",
                content="The auth token must be rotated daily.",
                token_count=9,
            ))

            handlers = MethodHandlers.__new__(MethodHandlers)
            handlers.session_repo = session_repo
            handlers.message_repo = msg_repo
            sent: list[str] = []

            class FakeWs:
                async def send_text(self, payload):
                    sent.append(payload)

            await handlers._session_search(FakeWs(), "r1", {"query": "auth token"}, "s1")
            import json
            payload = json.loads(sent[0])
            assert "error" not in payload or payload.get("error") is None
            assert payload["result"]["count"] >= 1
            assert payload["result"]["hits"][0]["session_id"] == "s1"
            assert "index_parity" in payload["result"]
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_search_handler_missing_query(self, temp_dir):
        from server.api.handlers import MethodHandlers
        from server.persistence.repositories import SessionRepository
        db = Database(str(temp_dir / "test.db"))
        await db.connect()
        try:
            handlers = MethodHandlers.__new__(MethodHandlers)
            handlers.session_repo = SessionRepository(db)
            sent: list[str] = []

            class FakeWs:
                async def send_text(self, payload):
                    sent.append(payload)

            await handlers._session_search(FakeWs(), "r1", {}, None)
            import json
            payload = json.loads(sent[0])
            assert payload["error"]["code"] == -32602
        finally:
            await db.close()
