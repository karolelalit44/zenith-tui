from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from ..connection import Database
from ..models import SessionWorkspaceRecord
from ..safe import safe_db


class SessionWorkspaceRepository:
    """Persist session workspace file records across server restarts.

    Each record tracks a file touched during a session with its content hash,
    size, operation counts, and monotonic timestamps for staleness detection.
    """

    def __init__(self, db: Database):
        self.db = db

    @safe_db("upsert_workspace", table="session_workspace")
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
        now = datetime.now().isoformat()
        stmt = (
            sqlite_upsert(SessionWorkspaceRecord)
            .values(
                id=str(_uuid.uuid4()),
                session_id=session_id,
                path=path,
                content_hash=content_hash,
                size=size,
                writes=writes,
                edits=edits,
                last_read_at=last_read_at,
                last_edited_at=last_edited_at,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["session_id", "path"],
                set_={
                    "content_hash": content_hash,
                    "size": size,
                    "writes": writes,
                    "edits": edits,
                    "last_read_at": last_read_at,
                    "last_edited_at": last_edited_at,
                    "updated_at": now,
                },
            )
        )
        async with self.db.session() as s:
            await s.execute(stmt)
            await s.commit()

    @safe_db("upsert_workspace_batch", table="session_workspace")
    async def upsert_batch(self, session_id: str, records: list[dict]) -> None:
        if not records:
            return
        now = datetime.now().isoformat()
        values = []
        for rec in records:
            values.append(
                {
                    "id": str(_uuid.uuid4()),
                    "session_id": session_id,
                    "path": rec["path"],
                    "content_hash": rec.get("content_hash", ""),
                    "size": rec.get("size", 0),
                    "writes": rec.get("writes", 0),
                    "edits": rec.get("edits", 0),
                    "last_read_at": rec.get("last_read_at", 0.0),
                    "last_edited_at": rec.get("last_edited_at", 0.0),
                    "created_at": now,
                    "updated_at": now,
                }
            )
        async with self.db.session() as s:
            for v in values:
                stmt = (
                    sqlite_upsert(SessionWorkspaceRecord)
                    .values(**v)
                    .on_conflict_do_update(
                        index_elements=["session_id", "path"],
                        set_={
                            "content_hash": v["content_hash"],
                            "size": v["size"],
                            "writes": v["writes"],
                            "edits": v["edits"],
                            "last_read_at": v["last_read_at"],
                            "last_edited_at": v["last_edited_at"],
                            "updated_at": v["updated_at"],
                        },
                    )
                )
                await s.execute(stmt)
            await s.commit()

    @safe_db("get_workspace", table="session_workspace")
    async def get_all(self, session_id: str) -> list[dict]:
        async with self.db.session() as s:
            rows = (
                (
                    await s.execute(
                        select(SessionWorkspaceRecord)
                        .where(SessionWorkspaceRecord.session_id == session_id)
                        .order_by(SessionWorkspaceRecord.last_edited_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return [
                {
                    "path": r.path,
                    "content_hash": r.content_hash,
                    "size": r.size,
                    "writes": r.writes,
                    "edits": r.edits,
                    "last_read_at": r.last_read_at,
                    "last_edited_at": r.last_edited_at,
                }
                for r in rows
            ]

    @safe_db("delete_workspace_session", table="session_workspace")
    async def delete_session(self, session_id: str) -> None:
        async with self.db.session() as s:
            await s.execute(
                delete(SessionWorkspaceRecord).where(
                    SessionWorkspaceRecord.session_id == session_id
                )
            )
            await s.commit()
