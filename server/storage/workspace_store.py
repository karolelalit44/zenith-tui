"""File-backed session workspace file-state registry.

State lives INSIDE the single per-session JSONL as ``wsfile`` records
(one latest-wins record per edited path) — no separate file.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from .atomic import append_jsonl_sync, read_jsonl, rewrite_jsonl_atomic
from .paths import StorageHome
from .session_file import load_snapshot, locate


def _now() -> str:
    return datetime.now().isoformat()


def _ws_record(path_key: str, existing: dict, rec: dict) -> dict:
    return {
        "t": "wsfile",
        "path": path_key,
        "content_hash": rec.get("content_hash", ""),
        "size": rec.get("size", 0),
        "writes": rec.get("writes", 0),
        "edits": rec.get("edits", 0),
        "last_read_at": rec.get("last_read_at", 0.0),
        "last_edited_at": rec.get("last_edited_at", 0.0),
        "created_at": existing.get("created_at", _now()),
        "updated_at": _now(),
    }


class FileWorkspaceRepository:
    def __init__(self, home: StorageHome):
        self.home = home

    async def upsert(
        self,
        session_id: str,
        path: str,
        content_hash: str,
        size: int,
        writes: int,
        edits: int,
        last_read_at: float,
        last_edited_at: float,
    ) -> None:
        await self.upsert_batch(session_id, [{
            "path": path,
            "content_hash": content_hash,
            "size": size,
            "writes": writes,
            "edits": edits,
            "last_read_at": last_read_at,
            "last_edited_at": last_edited_at,
        }])

    async def upsert_batch(self, session_id: str, records: list[dict]) -> None:
        if not records:
            return
        async with self.home.lock:
            snap = load_snapshot(self.home, session_id)
            state = snap["workspace"] if snap else {}
            file = locate(self.home, session_id)
            if file is None:
                raise ValueError(f"Session {session_id} not found")
            for rec in records:
                path_key = rec["path"]
                merged = _ws_record(path_key, state.get(path_key, {}), rec)
                state[path_key] = {k: v for k, v in merged.items() if k != "t"}
                append_jsonl_sync(file, merged)

    async def get_all(self, session_id: str) -> list[dict]:
        snap = await asyncio.to_thread(load_snapshot, self.home, session_id)
        records = list(snap["workspace"].values()) if snap else []
        records.sort(key=lambda r: float(r.get("last_edited_at", 0.0)), reverse=True)
        return [
            {
                "path": r["path"],
                "content_hash": r.get("content_hash", ""),
                "size": r.get("size", 0),
                "writes": r.get("writes", 0),
                "edits": r.get("edits", 0),
                "last_read_at": r.get("last_read_at", 0.0),
                "last_edited_at": r.get("last_edited_at", 0.0),
            }
            for r in records
        ]

    async def delete_session(self, session_id: str) -> None:
        """Drop all workspace records; keep every other record in the file."""
        async with self.home.lock:
            file = locate(self.home, session_id)
            if file is None:
                return
            kept = [r for r in read_jsonl(file) if r.get("t") != "wsfile"]
            rewrite_jsonl_atomic(file, kept)
