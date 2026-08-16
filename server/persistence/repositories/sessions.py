from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import delete, func, select, update

from server.domain.domain import ScenarioMode, SessionState
from server.domain.events import Event
from server.domain.message import Message
from server.domain.session import Session

from ..connection import Database
from ..models import MessageRecord, SessionRecord
from ..safe import safe_db
from .base import _iso


class SessionRepository:
    def __init__(self, db: Database):
        self.db = db

    @safe_db("create_session", table="sessions")
    async def create(self, session: Session) -> Session:
        async with self.db.session() as s:
            s.add(
                SessionRecord(
                    id=session.id,
                    title=session.title,
                    mode=session.mode.value if hasattr(session.mode, "value") else session.mode,
                    state=session.state.value if hasattr(session.state, "value") else session.state,
                    created_at=session.created_at.isoformat(),
                    updated_at=session.updated_at.isoformat(),
                    workspace_root=session.workspace_root,
                    is_active=session.is_active,
                    metadata_json=json.dumps(session.metadata),
                    parent_session_id=session.parent_session_id,
                    plan_output=session.plan_output,
                    plan_approved_at=_iso(session.plan_approved_at),
                    message_count=session.message_count,
                    total_tokens=session.total_tokens,
                    total_cost=session.total_cost,
                    model=session.model,
                    provider=session.provider,
                    agent_state=session.agent_state,
                    context_used=session.context_used,
                    context_window=session.context_window,
                    context_percent=session.context_percent,
                    error_count=session.error_count,
                    last_error=session.last_error,
                    export_format=session.export_format,
                    exported_at=_iso(session.exported_at),
                )
            )
            await s.commit()
        return session

    def _record_to_session(self, r: SessionRecord) -> Session:
        from server.domain.domain import ScenarioMode

        return Session(
            id=r.id,
            title=r.title,
            mode=ScenarioMode(r.mode) if r.mode else ScenarioMode.BUILD,
            state=SessionState(r.state or "created"),
            created_at=datetime.fromisoformat(r.created_at),
            updated_at=datetime.fromisoformat(r.updated_at),
            workspace_root=r.workspace_root,
            is_active=bool(r.is_active),
            metadata=json.loads(r.metadata_json or "{}"),
            parent_session_id=r.parent_session_id,
            plan_output=r.plan_output or "",
            plan_approved_at=datetime.fromisoformat(r.plan_approved_at)
            if r.plan_approved_at
            else None,
            message_count=r.message_count,
            total_tokens=r.total_tokens,
            total_cost=float(r.total_cost or 0),
            model=r.model,
            provider=r.provider,
            agent_state=r.agent_state or "idle",
            context_used=r.context_used,
            context_window=r.context_window,
            context_percent=float(r.context_percent or 0),
            error_count=r.error_count,
            last_error=r.last_error,
            export_format=r.export_format,
            exported_at=datetime.fromisoformat(r.exported_at) if r.exported_at else None,
        )

    @safe_db("get_session", table="sessions")
    async def get(self, session_id: str) -> Session | None:
        async with self.db.session() as s:
            rec = await s.get(SessionRecord, session_id)
            return self._record_to_session(rec) if rec else None

    @safe_db("list_sessions", table="sessions")
    async def list_active(self) -> list[Session]:
        async with self.db.session() as s:
            rows = (
                (
                    await s.execute(
                        select(SessionRecord)
                        .where(SessionRecord.is_active.is_(True))
                        .order_by(SessionRecord.updated_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return [self._record_to_session(r) for r in rows]

    @safe_db("list_sessions", table="sessions")
    async def list_all(
        self,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
        search: str | None = None,
        state_filter: str | None = None,
    ) -> list[Session]:
        stmt = select(SessionRecord)
        if not include_archived:
            stmt = stmt.where(SessionRecord.is_active.is_(True))
        if state_filter:
            stmt = stmt.where(SessionRecord.state == state_filter)
        if search:
            stmt = stmt.where(SessionRecord.title.like(f"%{search}%"))
        stmt = stmt.order_by(SessionRecord.updated_at.desc()).limit(limit).offset(offset)
        async with self.db.session() as s:
            rows = (await s.execute(stmt)).scalars().all()
            return [self._record_to_session(r) for r in rows]

    list = list_all

    @safe_db("list_sessions", table="sessions")
    async def get_summaries(self, limit: int = 10, include_archived: bool = False) -> list[dict]:
        async with self.db.session() as s:
            msg_count_sub = (
                select(
                    MessageRecord.session_id, func.count(MessageRecord.id).label("actual_msg_count")
                )
                .where(MessageRecord.role == "user")
                .group_by(MessageRecord.session_id)
                .subquery()
            )
            stmt = select(
                SessionRecord.id,
                SessionRecord.title,
                SessionRecord.mode,
                SessionRecord.state,
                SessionRecord.provider,
                SessionRecord.model,
                func.coalesce(msg_count_sub.c.actual_msg_count, SessionRecord.message_count).label(
                    "message_count"
                ),
                SessionRecord.total_tokens,
                SessionRecord.total_cost,
                SessionRecord.context_percent,
                SessionRecord.created_at,
                SessionRecord.updated_at,
                SessionRecord.is_active,
                SessionRecord.error_count,
                SessionRecord.last_error,
                SessionRecord.parent_session_id,
            ).outerjoin(msg_count_sub, SessionRecord.id == msg_count_sub.c.session_id)
            if not include_archived:
                stmt = stmt.where(SessionRecord.is_active.is_(True))
            stmt = stmt.where(
                (func.coalesce(msg_count_sub.c.actual_msg_count, SessionRecord.message_count) > 0)
                | (SessionRecord.total_tokens > 0)
            )
            stmt = stmt.order_by(SessionRecord.updated_at.desc()).limit(limit)
            rows = (await s.execute(stmt)).mappings().all()
            return [dict(r) for r in rows]

    @safe_db("update_session", table="sessions")
    async def update(self, session: Session) -> Session:
        session.updated_at = datetime.now()
        async with self.db.session() as s:
            rec = await s.get(SessionRecord, session.id)
            if rec is None:
                raise ValueError(f"Session {session.id} not found for update")
            rec.title = session.title
            rec.mode = session.mode.value if hasattr(session.mode, "value") else session.mode
            rec.state = session.state.value if hasattr(session.state, "value") else session.state
            rec.updated_at = session.updated_at.isoformat()
            rec.is_active = session.is_active
            rec.metadata_json = json.dumps(session.metadata)
            rec.parent_session_id = session.parent_session_id
            rec.plan_output = session.plan_output
            rec.plan_approved_at = _iso(session.plan_approved_at)
            rec.message_count = session.message_count
            rec.total_tokens = session.total_tokens
            rec.total_cost = session.total_cost
            rec.model = session.model
            rec.provider = session.provider
            rec.agent_state = session.agent_state
            rec.context_used = session.context_used
            rec.context_window = session.context_window
            rec.context_percent = session.context_percent
            rec.error_count = session.error_count
            rec.last_error = session.last_error
            rec.export_format = session.export_format
            rec.exported_at = _iso(session.exported_at)
            await s.commit()
        return session

    @safe_db("get_session", table="sessions")
    async def find_latest_with_plan(self) -> Session | None:
        async with self.db.session() as s:
            rec = (
                await s.execute(
                    select(SessionRecord)
                    .where(SessionRecord.plan_output != "", SessionRecord.is_active.is_(True))
                    .order_by(SessionRecord.updated_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not rec:
                return None
            return Session(
                id=rec.id,
                title=rec.title,
                mode=ScenarioMode(rec.mode) if rec.mode else ScenarioMode.BUILD,
                created_at=datetime.fromisoformat(rec.created_at),
                updated_at=datetime.fromisoformat(rec.updated_at),
                workspace_root=rec.workspace_root,
                is_active=bool(rec.is_active),
                metadata=json.loads(rec.metadata_json or "{}"),
                parent_session_id=rec.parent_session_id,
                state=SessionState(rec.state or "created"),
                plan_output=rec.plan_output or "",
                plan_approved_at=datetime.fromisoformat(rec.plan_approved_at)
                if rec.plan_approved_at
                else None,
            )

    @safe_db("delete_session", table="sessions")
    async def delete(self, session_id: str) -> bool:
        async with self.db.session() as s:
            await s.execute(delete(SessionRecord).where(SessionRecord.id == session_id))
            await s.commit()
        return True

    @safe_db("update_session", table="sessions")
    async def add_tokens(self, session_id: str, tokens: int, cost: float = 0.0) -> Session | None:
        session = await self.get(session_id)
        if not session:
            return None
        session.add_tokens(tokens, cost)
        return await self.update(session)


class MessageRepository:
    def __init__(self, db: Database):
        self.db = db

    @safe_db("create_message", table="messages")
    async def create(self, message: Message) -> Message:
        event_dicts = [e.model_dump() for e in message.events]
        async with self.db.session() as s:
            s.add(
                MessageRecord(
                    id=message.id,
                    session_id=message.session_id,
                    role=message.role,
                    content=message.content,
                    events_json=json.dumps(event_dicts),
                    token_count=message.token_count,
                    created_at=message.created_at.isoformat(),
                    metadata_json=json.dumps(message.metadata),
                )
            )
            srec = await s.get(SessionRecord, message.session_id)
            if srec:
                if message.role == "user":
                    srec.message_count += 1
                srec.updated_at = datetime.now().isoformat()
            await s.commit()
        return message

    append = create

    @safe_db("get_messages", table="messages")
    async def get_by_session(self, session_id: str, limit: int = 50) -> list[Message]:
        async with self.db.session() as s:
            rows = (
                (
                    await s.execute(
                        select(MessageRecord)
                        .where(MessageRecord.session_id == session_id)
                        .order_by(MessageRecord.created_at.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        messages = []
        for r in reversed(rows):
            events_data = json.loads(r.events_json or "[]")
            events = [Event(**e) for e in events_data]
            messages.append(
                Message(
                    id=r.id,
                    session_id=r.session_id,
                    role=r.role,
                    content=r.content,
                    events=events,
                    token_count=r.token_count,
                    created_at=datetime.fromisoformat(r.created_at),
                    metadata=json.loads(r.metadata_json or "{}"),
                )
            )
        return messages

    @safe_db("count_messages", table="messages")
    async def count_tokens(self, session_id: str) -> int:
        async with self.db.session() as s:
            total = (
                await s.execute(
                    select(func.coalesce(func.sum(MessageRecord.token_count), 0)).where(
                        MessageRecord.session_id == session_id
                    )
                )
            ).scalar_one()
            return int(total or 0)

    @safe_db("delete_messages", table="messages")
    async def delete_by_session(self, session_id: str) -> None:
        async with self.db.session() as s:
            await s.execute(delete(MessageRecord).where(MessageRecord.session_id == session_id))
            await s.commit()

    @safe_db("delete_messages", table="messages")
    async def delete_tool_results(self, session_id: str) -> int:
        async with self.db.session() as s:
            ids = (
                (
                    await s.execute(
                        select(MessageRecord.id).where(
                            MessageRecord.session_id == session_id, MessageRecord.role == "tool"
                        )
                    )
                )
                .scalars()
                .all()
            )
            if ids:
                await s.execute(delete(MessageRecord).where(MessageRecord.id.in_(list(ids))))
                await s.commit()
            return len(ids)

    @safe_db("update_messages", table="messages")
    async def strip_tool_events(self, session_id: str) -> int:
        from server.domain.events import EventKind

        async with self.db.session() as s:
            rows = (
                await s.execute(
                    select(MessageRecord.id, MessageRecord.events_json).where(
                        MessageRecord.session_id == session_id
                    )
                )
            ).all()
            touched = 0
            for rid, raw in rows:
                if not raw:
                    continue
                parsed = json.loads(raw)
                kept = [e for e in parsed if e.get("kind") != EventKind.TOOL_RESULT.value]
                if len(kept) == len(parsed):
                    continue
                await s.execute(
                    update(MessageRecord)
                    .where(MessageRecord.id == rid)
                    .values(events_json=json.dumps(kept))
                )
                touched += 1
            if touched:
                await s.commit()
            return touched
