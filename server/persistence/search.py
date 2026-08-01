"""Search repository — FTS5 full-text search over sessions and messages.

HP-9: virtual tables (message_fts, session_fts) are kept in sync with
`messages` and `sessions` via triggers (see 010_search_index.sql). Querying
uses SQLite's bm25() ranker for relevance-ordered results.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def _escape_query(query: str) -> str:
    """Escape an FTS5 MATCH query.

    Each token is quoted so special characters (e.g. quotes, `OR`, `*`) are
    treated literally. A bare phrase "auth token" becomes `"auth" "token"`.
    """
    tokens = []
    for t in re.split(r"\s+", query):
        t = t.strip().strip('"').strip()
        if t:
            tokens.append(f'"{t}"')
    return " ".join(tokens)


class SearchRepository:
    def __init__(self, db) -> None:
        self.db = db

    async def search(
        self,
        query: str,
        limit: int = 20,
        session_id: str | None = None,
    ) -> list[dict]:
        """Search messages and sessions. Returns ranked hits.

        Each hit has:
          type: "message" | "session"
          id, session_id, title, created_at
          snippet: highlighted content match (messages only)
        """
        pattern = _escape_query(query)
        if not pattern:
            return []

        hits: list[dict] = []

        # Messages (ranked by bm25)
        msg_sql = (
            "SELECT m.id, m.session_id, m.role, m.content, m.created_at, s.title,"
            "       snippet(message_fts, 0, '[', ']', '...', 12) AS snippet"
            "  FROM message_fts"
            "  JOIN messages m ON m.rowid = message_fts.rowid"
            "  JOIN sessions s ON s.id = m.session_id"
            "  WHERE message_fts MATCH ?"
            f"  {'AND m.session_id = ?' if session_id else ''}"
            "  ORDER BY bm25(message_fts)"
            f"  LIMIT {int(limit)}"
        )
        params: tuple = (pattern,) if not session_id else (pattern, session_id)
        for row in await self.db.fetch_all(msg_sql, params):
            hits.append({
                "type": "message",
                "id": row["id"],
                "session_id": row["session_id"],
                "title": row.get("title", ""),
                "role": row["role"],
                "created_at": row["created_at"],
                "snippet": row["snippet"],
            })

        # Sessions (by title), ranked by bm25
        sess_sql = (
            "SELECT s.id, s.title, s.created_at,"
            "       snippet(session_fts, 0, '[', ']', '...', 12) AS snippet"
            "  FROM session_fts"
            "  JOIN sessions s ON s.rowid = session_fts.rowid"
            "  WHERE session_fts MATCH ?"
            f"  {'AND s.id = ?' if session_id else ''}"
            "  ORDER BY bm25(session_fts)"
            f"  LIMIT {int(limit)}"
        )
        for row in await self.db.fetch_all(sess_sql, params):
            hits.append({
                "type": "session",
                "id": row["id"],
                "session_id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "snippet": row["snippet"],
            })

        return hits

    async def index_parity(self) -> dict:
        """Verify the FTS index is in sync with the source tables."""
        msg_count = await self.db.fetch_one("SELECT COUNT(*) AS n FROM messages")
        fts_count = await self.db.fetch_one("SELECT COUNT(*) AS n FROM message_fts")
        sess_count = await self.db.fetch_one("SELECT COUNT(*) AS n FROM sessions")
        sess_fts_count = await self.db.fetch_one("SELECT COUNT(*) AS n FROM session_fts")
        return {
            "messages": msg_count["n"] if msg_count else 0,
            "message_fts": fts_count["n"] if fts_count else 0,
            "sessions": sess_count["n"] if sess_count else 0,
            "session_fts": sess_fts_count["n"] if sess_fts_count else 0,
        }
