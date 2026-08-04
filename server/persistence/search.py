from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def _escape_query(query: str) -> str:
    tokens = []
    for t in re.split("\\s+", query):
        t = t.strip().strip('"').strip()
        if t:
            tokens.append(f'"{t}"')
    return " ".join(tokens)


class SearchRepository:
    def __init__(self, db) -> None:
        self.db = db

    async def search(
        self, query: str, limit: int = 20, session_id: str | None = None
    ) -> list[dict]:
        pattern = _escape_query(query)
        if not pattern:
            return []
        hits: list[dict] = []
        msg_sql = f"SELECT m.id, m.session_id, m.role, m.content, m.created_at, s.title, snippet(message_fts, 0, '[', ']', '...', 12) AS snippet FROM message_fts JOIN messages m ON m.rowid = message_fts.rowid JOIN sessions s ON s.id = m.session_id WHERE message_fts MATCH ? {('AND m.session_id = ?' if session_id else '')} ORDER BY bm25(message_fts) LIMIT {int(limit)}"
        params: tuple = (pattern,) if not session_id else (pattern, session_id)
        for row in await self.db.fetch_all(msg_sql, params):
            hits.append(
                {
                    "type": "message",
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "title": row.get("title", ""),
                    "role": row["role"],
                    "created_at": row["created_at"],
                    "snippet": row["snippet"],
                }
            )
        sess_sql = f"SELECT s.id, s.title, s.created_at, snippet(session_fts, 0, '[', ']', '...', 12) AS snippet FROM session_fts JOIN sessions s ON s.rowid = session_fts.rowid WHERE session_fts MATCH ? {('AND s.id = ?' if session_id else '')} ORDER BY bm25(session_fts) LIMIT {int(limit)}"
        for row in await self.db.fetch_all(sess_sql, params):
            hits.append(
                {
                    "type": "session",
                    "id": row["id"],
                    "session_id": row["id"],
                    "title": row["title"],
                    "created_at": row["created_at"],
                    "snippet": row["snippet"],
                }
            )
        return hits

    async def index_parity(self) -> dict:
        from sqlalchemy import func, select

        from server.persistence.models import MessageRecord, SessionRecord

        async with self.db.session() as s:
            msg_count = (
                await s.execute(select(func.count()).select_from(MessageRecord))
            ).scalar() or 0
            sess_count = (
                await s.execute(select(func.count()).select_from(SessionRecord))
            ).scalar() or 0
        fts_count = await self.db.fetch_one("SELECT COUNT(*) AS n FROM message_fts")
        sess_fts_count = await self.db.fetch_one("SELECT COUNT(*) AS n FROM session_fts")
        return {
            "messages": msg_count,
            "message_fts": fts_count["n"] if fts_count else 0,
            "sessions": sess_count,
            "session_fts": sess_fts_count["n"] if sess_fts_count else 0,
        }
