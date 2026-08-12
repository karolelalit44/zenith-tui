from __future__ import annotations

import json
import uuid as _uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select

from ..blob_store import BlobStore
from ..connection import Database
from ..models import (
    SessionCheckpointRecord,
    SessionDraftRecord,
    SessionStatusHistoryRecord,
    SyncEventRecord,
)
from ..safe import safe_db


class CheckpointRepository:
    def __init__(self, db: Database):
        self.db = db

    @safe_db("create_checkpoint", table="session_checkpoints")
    async def create(
        self,
        session_id: str,
        checkpoint_type: str = "automatic",
        step_index: int = 0,
        snapshot_data: dict | None = None,
        token_count: int = 0,
        message_count: int = 0,
    ) -> str:
        cid = str(_uuid.uuid4())
        async with self.db.session() as s:
            s.add(
                SessionCheckpointRecord(
                    id=cid,
                    session_id=session_id,
                    checkpoint_type=checkpoint_type,
                    step_index=step_index,
                    snapshot_data=json.dumps(snapshot_data or {}),
                    token_count=token_count,
                    message_count=message_count,
                    created_at=datetime.now().isoformat(),
                )
            )
            await s.commit()
        return cid

    @safe_db("get_checkpoint", table="session_checkpoints")
    async def get_latest(self, session_id: str) -> dict | None:
        async with self.db.session() as s:
            rec = (
                await s.execute(
                    select(SessionCheckpointRecord)
                    .where(SessionCheckpointRecord.session_id == session_id)
                    .order_by(SessionCheckpointRecord.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if rec:
                result = {
                    c.name: getattr(rec, c.name) for c in SessionCheckpointRecord.__table__.columns
                }
                result["snapshot_data"] = json.loads(result["snapshot_data"])
                return result
            return None


class SyncEventRepository:
    def __init__(self, db: Database):
        self.db = db
        self._blob_store = BlobStore.from_db_path(db.db_path)

    @safe_db("record_sync_event", table="sync_events")
    async def record(
        self,
        session_id: str,
        event_type: str,
        event_data: dict,
        sequence: int | None = None,
        created_at: str | None = None,
    ) -> str:
        seq = sequence if sequence is not None else await self._next_sequence(session_id)
        eid = str(_uuid.uuid4())
        async with self.db.session() as s:
            s.add(
                SyncEventRecord(
                    id=eid,
                    session_id=session_id,
                    event_type=event_type,
                    event_data=json.dumps(self._blob_store.pack(event_data)),
                    sequence=seq,
                    created_at=created_at or datetime.now().isoformat(),
                )
            )
            await s.commit()
        return eid

    @safe_db("get_sync_events", table="sync_events")
    async def _next_sequence(self, session_id: str) -> int:
        async with self.db.session() as s:
            max_seq = (
                await s.execute(
                    select(func.coalesce(func.max(SyncEventRecord.sequence), 0)).where(
                        SyncEventRecord.session_id == session_id
                    )
                )
            ).scalar_one()
            return int(max_seq or 0) + 1

    @safe_db("get_sync_events", table="sync_events")
    async def get_since(self, session_id: str, sequence: int = 0) -> list[dict]:
        async with self.db.session() as s:
            rows = (
                (
                    await s.execute(
                        select(SyncEventRecord)
                        .where(
                            SyncEventRecord.session_id == session_id,
                            SyncEventRecord.sequence > sequence,
                        )
                        .order_by(SyncEventRecord.sequence.asc())
                    )
                )
                .scalars()
                .all()
            )
        result = []
        for r in rows:
            d = {c.name: getattr(r, c.name) for c in SyncEventRecord.__table__.columns}
            d["event_data"] = self._blob_store.unpack(json.loads(d["event_data"]))
            result.append(d)
        return result

    @safe_db("get_sync_events", table="sync_events")
    async def get_latest_sequence(self, session_id: str) -> int:
        async with self.db.session() as s:
            max_seq = (
                await s.execute(
                    select(func.coalesce(func.max(SyncEventRecord.sequence), 0)).where(
                        SyncEventRecord.session_id == session_id
                    )
                )
            ).scalar_one()
            return int(max_seq or 0)

    @safe_db("delete_sync_events", table="sync_events")
    async def delete_by_session(self, session_id: str) -> None:
        async with self.db.session() as s:
            await s.execute(delete(SyncEventRecord).where(SyncEventRecord.session_id == session_id))
            await s.commit()


class SessionStatusHistoryRepository:
    def __init__(self, db: Database):
        self.db = db

    @safe_db("record_status_history", table="session_status_history")
    async def record(
        self, session_id: str, from_state: str | None, to_state: str, reason: str = ""
    ) -> str:
        hid = str(_uuid.uuid4())
        async with self.db.session() as s:
            s.add(
                SessionStatusHistoryRecord(
                    id=hid,
                    session_id=session_id,
                    from_state=from_state,
                    to_state=to_state,
                    reason=reason,
                    created_at=datetime.now().isoformat(),
                )
            )
            await s.commit()
        return hid

    @safe_db("get_status_history", table="session_status_history")
    async def get_history(self, session_id: str, limit: int = 50) -> list[dict]:
        async with self.db.session() as s:
            rows = (
                (
                    await s.execute(
                        select(SessionStatusHistoryRecord)
                        .where(SessionStatusHistoryRecord.session_id == session_id)
                        .order_by(SessionStatusHistoryRecord.created_at.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return [
                {c.name: getattr(r, c.name) for c in SessionStatusHistoryRecord.__table__.columns}
                for r in rows
            ]


class DraftRepository:
    def __init__(self, db: Database):
        self.db = db

    @safe_db("save_draft", table="session_drafts")
    async def save(
        self, session_id: str, prompt: str = "", context: dict | None = None, ttl_hours: int = 24
    ) -> str:
        did = str(_uuid.uuid4())
        expires = (datetime.now() + timedelta(hours=ttl_hours)).isoformat()
        async with self.db.session() as s:
            s.add(
                SessionDraftRecord(
                    id=did,
                    session_id=session_id,
                    prompt=prompt,
                    context=json.dumps(context or {}),
                    expires_at=expires,
                    created_at=datetime.now().isoformat(),
                )
            )
            await s.commit()
        return did

    @safe_db("get_draft", table="session_drafts")
    async def get_by_session(self, session_id: str) -> dict | None:
        async with self.db.session() as s:
            rec = (
                await s.execute(
                    select(SessionDraftRecord)
                    .where(SessionDraftRecord.session_id == session_id)
                    .order_by(SessionDraftRecord.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if rec:
                result = {
                    c.name: getattr(rec, c.name) for c in SessionDraftRecord.__table__.columns
                }
                result["context"] = json.loads(result["context"])
                return result
            return None
