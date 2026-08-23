"""Linear-scan session/message search — replaces the FTS5 SearchRepository.

Same result shapes as the legacy implementation; ranking is recency-based
instead of bm25 (acceptable at local scale, decision D11/D20). The scan is
synchronous filesystem work and runs in a worker thread so the event loop
never blocks on large histories.
"""

from __future__ import annotations

import asyncio
import logging

from .paths import StorageHome
from .session_file import iter_records, iter_session_files

logger = logging.getLogger(__name__)

_SNIPPET_RADIUS = 60


def _snippet(text: str, needle: str) -> str:
    low = text.lower()
    idx = low.find(needle.lower())
    if idx < 0:
        return text[: _SNIPPET_RADIUS * 2] + ("..." if len(text) > _SNIPPET_RADIUS * 2 else "")
    start = max(0, idx - _SNIPPET_RADIUS)
    end = min(len(text), idx + len(needle) + _SNIPPET_RADIUS)
    prefix = "[" if start == 0 else "..."
    suffix = "]" if end == len(text) else "..."
    return f"{prefix}{text[start:end]}{suffix}"


class FileSearchRepository:
    def __init__(self, home: StorageHome):
        self.home = home

    async def search(
        self, query: str, limit: int = 20, session_id: str | None = None
    ) -> list[dict]:
        needle = (query or "").strip().lower()
        if not needle:
            return []
        return await asyncio.to_thread(self._search_sync, needle, limit, session_id)

    def _search_sync(
        self, needle: str, limit: int, session_id: str | None
    ) -> list[dict]:
        hits: list[dict] = []
        candidates = iter_session_files(self.home)
        if session_id:
            from .session_file import locate

            target = locate(self.home, session_id)
            candidates = [target] if target in candidates else ([target] if target else [])

        for path in candidates:
            sid = path.stem
            fields = _fields_of(self.home, sid, path)
            if fields is None:
                continue
            title = str(fields.get("title", ""))
            if needle in title.lower():
                hits.append(
                    {
                        "type": "session",
                        "id": sid,
                        "session_id": sid,
                        "title": title,
                        "created_at": fields.get("created_at", ""),
                        "snippet": _snippet(title, needle),
                    }
                )
                if len(hits) >= limit:
                    return hits
            for rec in iter_records(self.home, sid):
                if rec.get("t") != "msg":
                    continue
                content = str(rec.get("content") or "")
                if needle not in content.lower():
                    continue
                hits.append(
                    {
                        "type": "message",
                        "id": rec.get("id"),
                        "session_id": sid,
                        "title": title,
                        "role": rec.get("role"),
                        "created_at": rec.get("created_at"),
                        "snippet": _snippet(content, needle),
                    }
                )
                if len(hits) >= limit:
                    return hits
        return hits

    async def index_parity(self) -> dict:
        """Real storage counts.

        Search is a linear scan; there is no secondary/FTS index anymore,
        so no parity-vs-FTS metrics are reported.
        """
        return await asyncio.to_thread(self._parity_sync)

    def _parity_sync(self) -> dict:
        messages = 0
        sessions = 0
        for path in iter_session_files(self.home):
            sessions += 1
            messages += sum(
                1 for r in iter_records(self.home, path.stem) if r.get("t") == "msg"
            )
        return {"mode": "linear-scan", "messages": messages, "sessions": sessions}


def _fields_of(home: StorageHome, sid: str, path):
    from .session_file import tail_or_full_fields

    try:
        fields = tail_or_full_fields(path)
    except OSError:
        return None
    return fields or None
