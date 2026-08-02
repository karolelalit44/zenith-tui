import json
import uuid as _uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select, text, update

from server.domain.events import Event
from server.domain.domain import SessionState
from server.domain.message import Message
from server.domain.session import Session

from .blob_store import BlobStore
from .connection import Database
from .models import (
    AppSettingRecord,
    BudgetSettingsRecord,
    ContextDegradationRecord,
    MessageRecord,
    ProviderModelRecord,
    ProviderRecord,
    SessionCheckpointRecord,
    SessionDraftRecord,
    SessionRecord,
    SessionStatusHistoryRecord,
    SyncEventRecord,
    TokenUsageRecord,
)
from .safe import safe_db

CATALOG_PATH = Path(__file__).parent.parent / "config" / "provider_catalog.json"


def load_catalog() -> dict:
    """Load the provider catalog from the canonical JSON file."""
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


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
            plan_approved_at=datetime.fromisoformat(r.plan_approved_at) if r.plan_approved_at else None,
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
                await s.execute(
                    select(SessionRecord)
                    .where(SessionRecord.is_active == True)  # noqa: E712
                    .order_by(SessionRecord.updated_at.desc())
                )
            ).scalars().all()
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
            stmt = stmt.where(SessionRecord.is_active == True)  # noqa: E712
        if state_filter:
            stmt = stmt.where(SessionRecord.state == state_filter)
        if search:
            stmt = stmt.where(SessionRecord.title.like(f"%{search}%"))
        stmt = stmt.order_by(SessionRecord.updated_at.desc()).limit(limit).offset(offset)
        async with self.db.session() as s:
            rows = (await s.execute(stmt)).scalars().all()
            return [self._record_to_session(r) for r in rows]

    @safe_db("list_sessions", table="sessions")
    async def get_summaries(
        self,
        limit: int = 10,
        include_archived: bool = False,
    ) -> list[dict]:
        async with self.db.session() as s:
            msg_count_sub = (
                select(MessageRecord.session_id, func.count(MessageRecord.id).label("actual_msg_count"))
                .where(MessageRecord.role == "user")
                .group_by(MessageRecord.session_id)
                .subquery()
            )

            stmt = (
                select(
                    SessionRecord.id,
                    SessionRecord.title,
                    SessionRecord.mode,
                    SessionRecord.state,
                    SessionRecord.provider,
                    SessionRecord.model,
                    func.coalesce(msg_count_sub.c.actual_msg_count, SessionRecord.message_count).label("message_count"),
                    SessionRecord.total_tokens,
                    SessionRecord.total_cost,
                    SessionRecord.context_percent,
                    SessionRecord.created_at,
                    SessionRecord.updated_at,
                    SessionRecord.is_active,
                    SessionRecord.error_count,
                    SessionRecord.last_error,
                    SessionRecord.parent_session_id,
                )
                .outerjoin(msg_count_sub, SessionRecord.id == msg_count_sub.c.session_id)
            )
            if not include_archived:
                stmt = stmt.where(SessionRecord.is_active == True)  # noqa: E712
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
                    .where(SessionRecord.plan_output != "", SessionRecord.is_active == True)  # noqa: E712
                    .order_by(SessionRecord.updated_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not rec:
                return None
            return Session(
                id=rec.id,
                title=rec.title,
                mode=rec.mode,
                created_at=datetime.fromisoformat(rec.created_at),
                updated_at=datetime.fromisoformat(rec.updated_at),
                workspace_root=rec.workspace_root,
                is_active=bool(rec.is_active),
                metadata=json.loads(rec.metadata_json or "{}"),
                parent_session_id=rec.parent_session_id,
                state=rec.state or "created",
                plan_output=rec.plan_output or "",
                plan_approved_at=datetime.fromisoformat(rec.plan_approved_at) if rec.plan_approved_at else None,
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
        self._blob_store = BlobStore.from_db_path(db.db_path)

    @safe_db("create_message", table="messages")
    async def create(self, message: Message) -> Message:
        packed_events = [self._blob_store.pack(e.model_dump()) for e in message.events]
        async with self.db.session() as s:
            s.add(
                MessageRecord(
                    id=message.id,
                    session_id=message.session_id,
                    role=message.role,
                    content=message.content,
                    events_json=json.dumps(packed_events),
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

    @safe_db("get_messages", table="messages")
    async def get_by_session(self, session_id: str, limit: int = 50) -> list[Message]:
        async with self.db.session() as s:
            rows = (
                await s.execute(
                    select(MessageRecord)
                    .where(MessageRecord.session_id == session_id)
                    .order_by(MessageRecord.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
        messages = []
        for r in reversed(rows):
            events_data = json.loads(r.events_json or "[]")
            events = [Event(**self._blob_store.unpack(e)) for e in events_data]
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
        """Delete tool-result messages for a session. Returns rows removed."""
        async with self.db.session() as s:
            ids = (
                await s.execute(
                    select(MessageRecord.id).where(
                        MessageRecord.session_id == session_id, MessageRecord.role == "tool"
                    )
                )
            ).scalars().all()
            if ids:
                await s.execute(delete(MessageRecord).where(MessageRecord.id.in_(list(ids))))
                await s.commit()
            return len(ids)

    @safe_db("update_messages", table="messages")
    async def strip_tool_events(self, session_id: str) -> int:
        """Remove TOOL_RESULT events from persisted messages (Claude Code
        clear_tool_uses analogue). Returns rows touched."""
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
                unpacked = [self._blob_store.unpack(e) for e in json.loads(raw)]
                kept = [e for e in unpacked if e.get("kind") != EventKind.TOOL_RESULT.value]
                if len(kept) == len(unpacked):
                    continue
                packed = [self._blob_store.pack(e) for e in kept]
                await s.execute(
                    update(MessageRecord)
                    .where(MessageRecord.id == rid)
                    .values(events_json=json.dumps(packed))
                )
                touched += 1
            if touched:
                await s.commit()
            return touched


def _seed_providers_from_catalog(catalog: dict) -> list[dict]:
    """Convert catalog JSON to the seed data format expected by ensure_seeded()."""
    providers = []
    for pid, p in catalog["providers"].items():
        providers.append({
            "id": pid,
            "name": p["name"],
            "description": p.get("description", ""),
            "model": p["default_model"],
            "base_url": p["base_url"],
            "adapter": p.get("adapter", "openai_compat"),
            "capabilities": p.get("capabilities", {}),
            "api_key_prefix": p.get("api_key_prefix"),
            "swatch": p.get("swatch", []),
            "is_active": 1 if pid == catalog.get("default_active_provider") else 0,
            "models": [
                {
                    "id": m["id"],
                    "name": m["name"],
                    "context_window": m.get("context_window", 128000),
                    "is_default": 1 if m.get("is_default") else 0,
                }
                for m in p.get("models", [])
            ],
        })
    return providers


class ProviderRepositoryDB:
    def __init__(self, db: Database):
        self.db = db

    @safe_db("ensure_seeded", table="providers")
    async def ensure_seeded(self) -> None:
        """Reconcile catalog providers + models into SQLite (idempotent).

        Adds any catalog provider/model rows that are missing (so existing DBs
        pick up newly-added providers like ``openai_compatible`` / ``custom`` /
        ``tokenrouter``) and seeds the default active provider when none is set.
        Never overwrites existing rows — user-saved keys/URLs/models win.
        """
        async with self.db.session() as s:
            catalog = load_catalog()
            seed_providers = _seed_providers_from_catalog(catalog)
            default_provider = catalog.get("default_active_provider", "nvidia")
            now = datetime.now().isoformat()

            existing = {
                pid: True
                for pid in (await s.execute(select(ProviderRecord.id))).scalars().all()
            }

            for p in seed_providers:
                if p["id"] in existing:
                    continue
                s.add(
                    ProviderRecord(
                        id=p["id"],
                        name=p["name"],
                        description=p.get("description", ""),
                        api_key="",
                        model=p["model"],
                        base_url=p["base_url"],
                        max_tokens=4096,
                        temperature=0.7,
                        is_active=p["is_active"],
                        swatch_json=json.dumps(p["swatch"]),
                        adapter_type=p["adapter"],
                        capabilities_json=json.dumps(p["capabilities"]),
                        api_key_prefix=p["api_key_prefix"],
                        updated_at=now,
                    )
                )
            await s.flush()

            for p in seed_providers:
                if p["id"] not in existing:
                    existing[p["id"]] = True
                for m in p["models"]:
                    await s.execute(
                        text(
                            """
                            INSERT INTO provider_models (id, provider_id, name, context_window, description, is_default)
                            VALUES (:id, :provider_id, :name, :context_window, :description, :is_default)
                            ON CONFLICT(provider_id, id) DO NOTHING
                            """
                        ),
                        {
                            "id": m["id"],
                            "provider_id": p["id"],
                            "name": m["name"],
                            "context_window": m.get("context_window", 128000),
                            "description": m.get("description", ""),
                            "is_default": 1 if m.get("is_default") else 0,
                        },
                    )

            active = (
                await s.execute(
                    select(AppSettingRecord.value).where(AppSettingRecord.key == "active_provider")
                )
            ).scalar_one_or_none()
            if not active:
                await s.execute(
                    text(
                        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (:key, :value)"
                    ),
                    {"key": "active_provider", "value": default_provider},
                )
            await s.commit()

    @safe_db("get_active_provider", table="app_settings")
    async def get_active_provider_id(self) -> str:
        async with self.db.session() as s:
            row = (
                await s.execute(
                    select(AppSettingRecord.value).where(AppSettingRecord.key == "active_provider")
                )
            ).scalar_one_or_none()
            if row:
                return row
            active_id = (
                await s.execute(
                    select(ProviderRecord.id).where(ProviderRecord.is_active == True).limit(1)  # noqa: E712
                )
            ).scalar_one_or_none()
            return active_id or "nvidia"

    @safe_db("set_active_provider", table="providers")
    async def set_active_provider_id(self, provider_id: str) -> None:
        async with self.db.session() as s:
            await s.execute(update(ProviderRecord).values(is_active=False))
            await s.execute(
                update(ProviderRecord).where(ProviderRecord.id == provider_id).values(is_active=True)
            )
            await s.execute(
                text(
                    "INSERT OR REPLACE INTO app_settings (key, value) VALUES (:key, :value)"
                ),
                {"key": "active_provider", "value": provider_id},
            )
            await s.commit()

    async def _get_provider_with_models(self, s, provider_id: str) -> dict | None:
        rec = await s.get(ProviderRecord, provider_id)
        if not rec:
            return None
        models = (
            await s.execute(
                select(ProviderModelRecord)
                .where(ProviderModelRecord.provider_id == provider_id)
                .order_by(ProviderModelRecord.is_default.desc(), ProviderModelRecord.name)
            )
        ).scalars().all()
        p = {
            k: getattr(rec, k)
            for k in (
                "id", "name", "description", "api_key", "model", "base_url",
                "max_tokens", "temperature", "is_active", "swatch_json",
                "adapter_type", "capabilities_json", "api_key_prefix", "updated_at",
            )
        }
        p["models"] = [
            {
                "id": m.id,
                "name": m.name,
                "context_window": m.context_window,
                "description": m.description,
                "is_default": m.is_default,
            }
            for m in models
        ]
        p["swatch"] = json.loads(p.get("swatch_json") or "[]")
        return p

    @safe_db("get_provider", table="providers")
    async def get_provider(self, provider_id: str) -> dict | None:
        await self.ensure_seeded()
        async with self.db.session() as s:
            return await self._get_provider_with_models(s, provider_id)

    @safe_db("list_providers", table="providers")
    async def list_providers(self) -> dict[str, dict]:
        await self.ensure_seeded()
        async with self.db.session() as s:
            ids = (
                await s.execute(select(ProviderRecord.id))
            ).scalars().all()
            providers = {}
            for pid in ids:
                p = await self._get_provider_with_models(s, pid)
                if p:
                    providers[pid] = p
            return providers

    @safe_db("save_provider", table="providers")
    async def save_provider(
        self,
        provider_id: str,
        api_key: str = "",
        model: str = "",
        base_url: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        set_active: bool = True,
    ) -> None:
        await self.ensure_seeded()
        now = datetime.now().isoformat()
        async with self.db.session() as s:
            existing = await s.get(ProviderRecord, provider_id)
            if existing:
                new_key = api_key if api_key.strip() else existing.api_key
                new_model = model if model.strip() else existing.model
                new_base = base_url if base_url.strip() else existing.base_url
                existing.api_key = new_key
                existing.model = new_model
                existing.base_url = new_base
                existing.max_tokens = max_tokens
                existing.temperature = temperature
                existing.updated_at = now
            else:
                s.add(
                    ProviderRecord(
                        id=provider_id,
                        name=provider_id.title(),
                        description="",
                        api_key=api_key,
                        model=model,
                        base_url=base_url,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        is_active=False,
                        swatch_json="[]",
                        updated_at=now,
                    )
                )
            await s.flush()
            if set_active:
                await s.execute(update(ProviderRecord).values(is_active=False))
                await s.execute(
                    update(ProviderRecord).where(ProviderRecord.id == provider_id).values(is_active=True)
                )
                await s.execute(
                    text(
                        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (:key, :value)"
                    ),
                    {"key": "active_provider", "value": provider_id},
                )
            await s.commit()

    @safe_db("get_provider_models", table="provider_models")
    async def get_models_for_provider(self, provider_id: str) -> list[dict]:
        await self.ensure_seeded()
        async with self.db.session() as s:
            models = (
                await s.execute(
                    select(ProviderModelRecord).where(ProviderModelRecord.provider_id == provider_id)
                )
            ).scalars().all()
            return [
                {
                    "id": m.id,
                    "name": m.name,
                    "context_window": m.context_window,
                    "description": m.description,
                    "is_default": m.is_default,
                }
                for m in models
            ]


class TokenUsageRepository:
    def __init__(self, db: Database):
        self.db = db
        self._price_cache: dict[str, dict] | None = None

    def _resolve_price(self, provider: str, model: str) -> dict:
        if self._price_cache is None:
            self._price_cache = {}
            try:
                catalog = load_catalog()
                for prov_id, prov_data in catalog.get("providers", {}).items():
                    for m in prov_data.get("models", []):
                        p = m.get("pricing", {})
                        key = f"{prov_id}:{m['id']}"
                        self._price_cache[key] = {
                            "input": p.get("input", 0.0),
                            "output": p.get("output", 0.0),
                            "cache_read": p.get("cache_read", 0.0),
                            "cache_creation": p.get("cache_creation", 0.0),
                        }
            except Exception:
                pass
        lookup = f"{provider}:{model}"
        if lookup in self._price_cache:
            return self._price_cache[lookup]
        for key, val in self._price_cache.items():
            if key.endswith(f":{model}"):
                return val
        return {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_creation": 0.0}

    @safe_db("record_token_usage", table="token_usage")
    async def record(
        self,
        session_id: str,
        provider: str,
        model: str,
        total_tokens: int,
        context_window: int,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
        step_index: int = -1,
        estimated: bool = False,
    ) -> str:
        from datetime import datetime as _dt

        percent = (total_tokens / context_window * 100) if context_window > 0 else 0.0
        price = self._resolve_price(provider, model)
        if estimated:
            cost_usd = 0.0
        else:
            input_cost = (input_tokens or prompt_tokens) * price["input"] / 1_000_000
            output_cost = (output_tokens or completion_tokens) * price["output"] / 1_000_000
            cache_read_cost = (cache_read_tokens or 0) * price.get("cache_read", 0) / 1_000_000
            cache_creation_cost = (cache_creation_tokens or 0) * price.get("cache_creation", 0) / 1_000_000
            cost_usd = round(input_cost + output_cost + cache_read_cost + cache_creation_cost, 6)
        record_id = str(_uuid.uuid4())
        async with self.db.session() as s:
            s.add(
                TokenUsageRecord(
                    id=record_id,
                    session_id=session_id,
                    provider=provider,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    context_window=context_window,
                    percent=round(percent, 3),
                    created_at=_dt.now().isoformat(),
                    cost_usd=cost_usd,
                    input_tokens=input_tokens or prompt_tokens,
                    output_tokens=output_tokens or completion_tokens,
                    cache_read_tokens=cache_read_tokens,
                    cache_creation_tokens=cache_creation_tokens,
                    step_index=step_index,
                    estimated=estimated,
                )
            )
            await s.commit()
        return record_id

    @safe_db("record_degradation", table="context_degradation")
    async def record_degradation(
        self, session_id: str, step_index: int, before_tokens: int, after_tokens: int, reason: str
    ) -> None:
        from datetime import datetime as _dt

        async with self.db.session() as s:
            s.add(
                ContextDegradationRecord(
                    id=str(_uuid.uuid4()),
                    session_id=session_id,
                    step_index=step_index,
                    before_tokens=before_tokens,
                    after_tokens=after_tokens,
                    reason=reason,
                    created_at=_dt.now().isoformat(),
                )
            )
            await s.commit()

    @safe_db("seed_pricing", table="pricing")
    async def seed_pricing(self) -> None:
        from datetime import datetime as _dt

        try:
            catalog = load_catalog()
            now = _dt.now().isoformat()
            async with self.db.session() as s:
                for prov_id, prov_data in catalog.get("providers", {}).items():
                    for m in prov_data.get("models", []):
                        p = m.get("pricing", {})
                        await s.execute(
                            text(
                                """INSERT OR REPLACE INTO pricing
                                   (model_id, provider, input_1m, output_1m, cache_read_1m, cache_creation_1m, updated_at)
                                   VALUES (:model, :provider, :input, :output, :cache_read, :cache_creation, :updated)"""
                            ),
                            {
                                "model": m["id"],
                                "provider": prov_id,
                                "input": p.get("input", 0.0),
                                "output": p.get("output", 0.0),
                                "cache_read": p.get("cache_read", 0.0),
                                "cache_creation": p.get("cache_creation", 0.0),
                                "updated": now,
                            },
                        )
                await s.commit()
        except Exception:
            pass

    @safe_db("token_stats", table="token_usage")
    async def get_stats_by_model(self, since: str | None = None, until: str | None = None) -> list[dict]:
        stmt = (
            select(
                TokenUsageRecord.provider,
                TokenUsageRecord.model,
                func.count().label("request_count"),
                func.coalesce(func.sum(TokenUsageRecord.input_tokens), 0).label("total_input_tokens"),
                func.coalesce(func.sum(TokenUsageRecord.output_tokens), 0).label("total_output_tokens"),
                func.coalesce(func.sum(TokenUsageRecord.prompt_tokens), 0).label("total_prompt_tokens"),
                func.coalesce(func.sum(TokenUsageRecord.completion_tokens), 0).label("total_completion_tokens"),
                func.coalesce(func.sum(TokenUsageRecord.total_tokens), 0).label("total_tokens"),
                func.coalesce(func.sum(TokenUsageRecord.cost_usd), 0).label("total_cost_usd"),
                func.coalesce(func.sum(TokenUsageRecord.cache_read_tokens), 0).label("total_cache_read"),
                func.coalesce(func.sum(TokenUsageRecord.cache_creation_tokens), 0).label("total_cache_creation"),
                func.max(TokenUsageRecord.context_window).label("context_window"),
            )
            .where(TokenUsageRecord.step_index == -1)
            .group_by(TokenUsageRecord.provider, TokenUsageRecord.model)
            .order_by(func.sum(TokenUsageRecord.total_tokens).desc())
        )
        if since:
            stmt = stmt.where(TokenUsageRecord.created_at >= since)
        if until:
            stmt = stmt.where(TokenUsageRecord.created_at <= until)
        async with self.db.session() as s:
            rows = (await s.execute(stmt)).mappings().all()
            return [dict(r) for r in rows]

    @safe_db("token_stats", table="token_usage")
    async def get_total_stats(self, since: str | None = None, until: str | None = None) -> dict:
        stmt = select(
            func.count().label("total_requests"),
            func.coalesce(func.sum(TokenUsageRecord.total_tokens), 0).label("grand_total_tokens"),
            func.coalesce(func.sum(TokenUsageRecord.input_tokens), 0).label("grand_total_input"),
            func.coalesce(func.sum(TokenUsageRecord.output_tokens), 0).label("grand_total_output"),
            func.coalesce(func.sum(TokenUsageRecord.prompt_tokens), 0).label("grand_total_prompt"),
            func.coalesce(func.sum(TokenUsageRecord.completion_tokens), 0).label("grand_total_completion"),
            func.coalesce(func.sum(TokenUsageRecord.cost_usd), 0).label("grand_total_cost_usd"),
            func.coalesce(func.sum(TokenUsageRecord.cache_read_tokens), 0).label("grand_total_cache_read"),
            func.coalesce(func.sum(TokenUsageRecord.cache_creation_tokens), 0).label("grand_total_cache_creation"),
            func.count(func.distinct(TokenUsageRecord.provider + ":" + TokenUsageRecord.model)).label("unique_models"),
        ).where(TokenUsageRecord.step_index == -1)
        if since:
            stmt = stmt.where(TokenUsageRecord.created_at >= since)
        if until:
            stmt = stmt.where(TokenUsageRecord.created_at <= until)
        async with self.db.session() as s:
            row = (await s.execute(stmt)).mappings().first()
            return dict(row) if row else {}

    @safe_db("token_stats", table="token_usage")
    async def get_cost_summary(self, period: str = "all") -> list[dict]:
        from datetime import datetime as _dt

        now = _dt.now()
        since = None
        if period == "day":
            since = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif period == "week":
            since = (now - timedelta(days=7)).isoformat()
        elif period == "month":
            since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        stmt = (
            select(
                TokenUsageRecord.provider,
                TokenUsageRecord.model,
                func.count().label("requests"),
                func.coalesce(func.sum(TokenUsageRecord.total_tokens), 0).label("total_tokens"),
                func.coalesce(func.sum(TokenUsageRecord.cost_usd), 0).label("total_cost"),
                func.coalesce(func.sum(TokenUsageRecord.input_tokens), 0).label("total_input"),
                func.coalesce(func.sum(TokenUsageRecord.output_tokens), 0).label("total_output"),
            )
            .where(TokenUsageRecord.step_index == -1)
            .group_by(TokenUsageRecord.provider, TokenUsageRecord.model)
            .order_by(func.sum(TokenUsageRecord.cost_usd).desc())
        )
        if since:
            stmt = stmt.where(TokenUsageRecord.created_at >= since)
        async with self.db.session() as s:
            rows = (await s.execute(stmt)).mappings().all()
            return [dict(r) for r in rows]

    @safe_db("get_budget_status", table="budget_settings")
    async def get_budget_status(self, session_id: str) -> dict:
        from datetime import datetime as _dt

        async with self.db.session() as s:
            rec = (
                await s.execute(
                    select(BudgetSettingsRecord)
                    .where(BudgetSettingsRecord.session_id == session_id, BudgetSettingsRecord.active == True)  # noqa: E712
                    .order_by(BudgetSettingsRecord.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not rec:
                return {"active": False, "max_session_cost": 0, "max_daily_cost": 0, "max_monthly_cost": 0}

            now = _dt.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

            async def cost(gte: str | None = None) -> float:
                stmt = select(func.coalesce(func.sum(TokenUsageRecord.cost_usd), 0)).where(
                    TokenUsageRecord.session_id == session_id
                )
                if gte:
                    stmt = stmt.where(TokenUsageRecord.created_at >= gte)
                return float((await s.execute(stmt)).scalar_one())

            return {
                "active": True,
                "max_session_cost": rec.max_session_cost,
                "max_daily_cost": rec.max_daily_cost,
                "max_monthly_cost": rec.max_monthly_cost,
                "session_cost": await cost(),
                "daily_cost": await cost(today_start),
                "monthly_cost": await cost(month_start),
            }

    @safe_db("upsert_budget", table="budget_settings")
    async def upsert_budget(self, session_id: str, max_session_cost: float, max_daily_cost: float, max_monthly_cost: float, active: bool = True) -> None:
        from datetime import datetime as _dt

        now = _dt.now().isoformat()
        async with self.db.session() as s:
            s.add(
                BudgetSettingsRecord(
                    id=str(_uuid.uuid4()),
                    session_id=session_id,
                    max_session_cost=max_session_cost,
                    max_daily_cost=max_daily_cost,
                    max_monthly_cost=max_monthly_cost,
                    active=active,
                    created_at=now,
                    updated_at=now,
                )
            )
            await s.commit()

    @safe_db("get_per_step_stats", table="token_usage")
    async def get_per_step_stats(self, session_id: str) -> list[dict]:
        async with self.db.session() as s:
            rows = (
                await s.execute(
                    select(TokenUsageRecord)
                    .where(TokenUsageRecord.session_id == session_id, TokenUsageRecord.step_index >= 0)
                    .order_by(TokenUsageRecord.step_index.asc())
                )
            ).scalars().all()
            return [self._record_to_dict(r) for r in rows]

    def _record_to_dict(self, r: TokenUsageRecord) -> dict:
        return {c.name: getattr(r, c.name) for c in TokenUsageRecord.__table__.columns}

    @safe_db("get_efficiency", table="token_usage")
    async def get_efficiency(self, session_id: str) -> dict:
        async with self.db.session() as s:
            total_row = (
                await s.execute(
                    select(
                        func.coalesce(func.sum(TokenUsageRecord.total_tokens), 0).label("total_consumed"),
                        func.coalesce(func.sum(TokenUsageRecord.cost_usd), 0).label("total_cost"),
                    ).where(TokenUsageRecord.session_id == session_id)
                )
            ).mappings().one()
            final_row = (
                await s.execute(
                    select(TokenUsageRecord.total_tokens.label("final_context"))
                    .where(TokenUsageRecord.session_id == session_id, TokenUsageRecord.step_index == -1)
                    .order_by(TokenUsageRecord.created_at.desc())
                    .limit(1)
                )
            ).mappings().first()
            deg_rows = (
                await s.execute(
                    select(
                        func.count().label("count"),
                        func.coalesce(
                            func.sum(ContextDegradationRecord.before_tokens - ContextDegradationRecord.after_tokens), 0
                        ).label("waste"),
                    ).where(ContextDegradationRecord.session_id == session_id)
                )
            ).mappings().one()

        total_consumed = int(total_row["total_consumed"] or 0)
        total_cost = float(total_row["total_cost"] or 0)
        final_context = int(final_row["final_context"] or 0) if final_row else 0
        deg = dict(deg_rows)
        waste_ratio = (deg["waste"] / total_consumed) if total_consumed > 0 else 0.0
        return {
            "total_tokens_consumed": total_consumed,
            "total_cost_usd": total_cost,
            "final_context_used": final_context,
            "waste_ratio": round(waste_ratio, 4),
            "summarization_count": deg["count"],
            "average_context_utilization": round(final_context / total_consumed, 4) if total_consumed > 0 else 0.0,
        }

    @safe_db("get_session_token_usage", table="token_usage")
    async def get_session_token_usage(self, session_id: str) -> list[dict]:
        async with self.db.session() as s:
            rows = (
                await s.execute(
                    select(TokenUsageRecord)
                    .where(TokenUsageRecord.session_id == session_id)
                    .order_by(TokenUsageRecord.created_at.asc())
                )
            ).scalars().all()
            return [self._record_to_dict(r) for r in rows]

    @safe_db("record_token_usage", table="token_usage")
    async def record_v2(
        self,
        session_id: str,
        provider: str,
        model: str,
        total_tokens: int,
        context_window: int,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
        cache_write_tokens: int = 0,
        reasoning_tokens: int = 0,
        step_index: int = -1,
        estimated: bool = False,
        is_retry: bool = False,
        retry_of: str | None = None,
        duration_ms: int = 0,
    ) -> str:
        percent = (total_tokens / context_window * 100) if context_window > 0 else 0.0
        price = self._resolve_price(provider, model)
        if estimated:
            cost_usd = 0.0
        else:
            input_cost = (input_tokens or prompt_tokens) * price["input"] / 1_000_000
            output_cost = (output_tokens or completion_tokens) * price["output"] / 1_000_000
            cache_read_cost = (cache_read_tokens or 0) * price.get("cache_read", 0) / 1_000_000
            cache_creation_cost = (cache_creation_tokens or 0) * price.get("cache_creation", 0) / 1_000_000
            cost_usd = round(input_cost + output_cost + cache_read_cost + cache_creation_cost, 6)
        record_id = str(_uuid.uuid4())
        async with self.db.session() as s:
            s.add(
                TokenUsageRecord(
                    id=record_id,
                    session_id=session_id,
                    provider=provider,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    context_window=context_window,
                    percent=round(percent, 3),
                    created_at=datetime.now().isoformat(),
                    cost_usd=cost_usd,
                    input_tokens=input_tokens or prompt_tokens,
                    output_tokens=output_tokens or completion_tokens,
                    cache_read_tokens=cache_read_tokens,
                    cache_creation_tokens=cache_creation_tokens,
                    cache_write_tokens=cache_write_tokens,
                    reasoning_tokens=reasoning_tokens,
                    step_index=step_index,
                    estimated=estimated,
                    is_retry=is_retry,
                    retry_of=retry_of,
                    duration_ms=duration_ms,
                )
            )
            await s.commit()
        return record_id

    @safe_db("get_lifetime_stats", table="token_usage")
    async def get_lifetime_stats(self) -> dict:
        async with self.db.session() as s:
            row = (
                await s.execute(
                    select(
                        func.count().label("total_requests"),
                        func.coalesce(func.sum(TokenUsageRecord.total_tokens), 0).label("grand_total_tokens"),
                        func.coalesce(func.sum(TokenUsageRecord.cost_usd), 0).label("grand_total_cost"),
                        func.coalesce(func.sum(TokenUsageRecord.input_tokens), 0).label("grand_total_input"),
                        func.coalesce(func.sum(TokenUsageRecord.output_tokens), 0).label("grand_total_output"),
                        func.coalesce(func.sum(TokenUsageRecord.cache_read_tokens), 0).label("grand_total_cache_read"),
                        func.coalesce(func.sum(TokenUsageRecord.cache_creation_tokens), 0).label("grand_total_cache_write"),
                        func.coalesce(func.sum(TokenUsageRecord.reasoning_tokens), 0).label("grand_total_reasoning"),
                        func.count(func.distinct(TokenUsageRecord.session_id)).label("total_sessions"),
                    )
                )
            ).mappings().first()
            return dict(row) if row else {}


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
                result = {c.name: getattr(rec, c.name) for c in SessionCheckpointRecord.__table__.columns}
                result["snapshot_data"] = json.loads(result["snapshot_data"])
                return result
            return None

    @safe_db("list_checkpoints", table="session_checkpoints")
    async def list_by_session(self, session_id: str, limit: int = 20) -> list[dict]:
        async with self.db.session() as s:
            rows = (
                await s.execute(
                    select(SessionCheckpointRecord)
                    .where(SessionCheckpointRecord.session_id == session_id)
                    .order_by(SessionCheckpointRecord.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
        result = []
        for r in rows:
            d = {c.name: getattr(r, c.name) for c in SessionCheckpointRecord.__table__.columns}
            d["snapshot_data"] = json.loads(d["snapshot_data"])
            result.append(d)
        return result

    @safe_db("delete_checkpoints", table="session_checkpoints")
    async def delete_old(self, session_id: str, keep: int = 5) -> int:
        async with self.db.session() as s:
            ids = (
                await s.execute(
                    select(SessionCheckpointRecord.id)
                    .where(SessionCheckpointRecord.session_id == session_id)
                    .order_by(SessionCheckpointRecord.created_at.desc())
                    .offset(keep)
                )
            ).scalars().all()
            ids = list(ids)
            if not ids:
                return 0
            await s.execute(delete(SessionCheckpointRecord).where(SessionCheckpointRecord.id.in_(ids)))
            await s.commit()
            return len(ids)


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
                await s.execute(
                    select(SyncEventRecord)
                    .where(SyncEventRecord.session_id == session_id, SyncEventRecord.sequence > sequence)
                    .order_by(SyncEventRecord.sequence.asc())
                )
            ).scalars().all()
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
    async def record(self, session_id: str, from_state: str | None, to_state: str, reason: str = "") -> str:
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
                await s.execute(
                    select(SessionStatusHistoryRecord)
                    .where(SessionStatusHistoryRecord.session_id == session_id)
                    .order_by(SessionStatusHistoryRecord.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
            return [
                {c.name: getattr(r, c.name) for c in SessionStatusHistoryRecord.__table__.columns}
                for r in rows
            ]


class DraftRepository:
    def __init__(self, db: Database):
        self.db = db

    @safe_db("save_draft", table="session_drafts")
    async def save(self, session_id: str, prompt: str = "", context: dict | None = None, ttl_hours: int = 24) -> str:
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
                result = {c.name: getattr(rec, c.name) for c in SessionDraftRecord.__table__.columns}
                result["context"] = json.loads(result["context"])
                return result
            return None

    @safe_db("list_drafts", table="session_drafts")
    async def list_expired(self) -> list[dict]:
        async with self.db.session() as s:
            rows = (
                await s.execute(
                    select(SessionDraftRecord).where(
                        SessionDraftRecord.expires_at < datetime.now().isoformat()
                    )
                )
            ).scalars().all()
            return [
                {c.name: getattr(r, c.name) for c in SessionDraftRecord.__table__.columns}
                for r in rows
            ]

    @safe_db("delete_drafts", table="session_drafts")
    async def delete_expired(self) -> int:
        rows = await self.list_expired()
        if not rows:
            return 0
        ids = [r["id"] for r in rows]
        async with self.db.session() as s:
            await s.execute(delete(SessionDraftRecord).where(SessionDraftRecord.id.in_(ids)))
            await s.commit()
        return len(ids)
