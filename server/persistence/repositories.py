import json
import uuid as _uuid
from datetime import datetime, timedelta
from pathlib import Path

from server.domain.events import Event
from server.domain.domain import SessionState
from server.domain.message import Message
from server.domain.session import Session

from .blob_store import BlobStore
from .connection import Database

CATALOG_PATH = Path(__file__).parent.parent / "config" / "provider_catalog.json"


def load_catalog() -> dict:
    """Load the provider catalog from the canonical JSON file."""
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class SessionRepository:
    def __init__(self, db: Database):
        self.db = db

    async def create(self, session: Session) -> Session:
        plan_approved = session.plan_approved_at.isoformat() if session.plan_approved_at else None
        await self.db.execute(
            """INSERT INTO sessions (id, title, mode, state, created_at, updated_at, workspace_root, is_active, metadata_json, parent_session_id, plan_output, plan_approved_at, message_count, total_tokens, total_cost, model, provider, agent_state, context_used, context_window, context_percent, error_count, last_error, export_format, exported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session.id,
                session.title,
                session.mode.value if hasattr(session.mode, 'value') else session.mode,
                session.state.value if hasattr(session.state, 'value') else session.state,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
                session.workspace_root,
                int(session.is_active),
                json.dumps(session.metadata),
                session.parent_session_id,
                session.plan_output,
                plan_approved,
                session.message_count,
                session.total_tokens,
                session.total_cost,
                session.model,
                session.provider,
                session.agent_state,
                session.context_used,
                session.context_window,
                session.context_percent,
                session.error_count,
                session.last_error,
                session.export_format,
                session.exported_at.isoformat() if session.exported_at else None,
            ),
        )
        await self.db.commit()
        return session

    def _row_to_session(self, row: dict) -> Session:
        from server.domain.domain import ScenarioMode
        plan_approved = datetime.fromisoformat(row["plan_approved_at"]) if row.get("plan_approved_at") else None
        exported_at = datetime.fromisoformat(row["exported_at"]) if row.get("exported_at") else None
        return Session(
            id=row["id"],
            title=row["title"],
            mode=ScenarioMode(row["mode"]) if row.get("mode") else ScenarioMode.BUILD,
            state=SessionState(row.get("state", "created")),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            workspace_root=row["workspace_root"],
            is_active=bool(row["is_active"]),
            metadata=json.loads(row["metadata_json"]),
            parent_session_id=row.get("parent_session_id"),
            plan_output=row.get("plan_output", ""),
            plan_approved_at=plan_approved,
            message_count=row.get("message_count", 0),
            total_tokens=row.get("total_tokens", 0),
            total_cost=float(row.get("total_cost", 0) or 0),
            model=row.get("model"),
            provider=row.get("provider"),
            agent_state=row.get("agent_state", "idle"),
            context_used=row.get("context_used", 0),
            context_window=row.get("context_window", 0),
            context_percent=float(row.get("context_percent", 0) or 0),
            error_count=row.get("error_count", 0),
            last_error=row.get("last_error"),
            export_format=row.get("export_format"),
            exported_at=exported_at,
        )

    async def get(self, session_id: str) -> Session | None:
        row = await self.db.fetch_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
        if not row:
            return None
        return self._row_to_session(row)

    async def list_active(self) -> list[Session]:
        rows = await self.db.fetch_all(
            "SELECT * FROM sessions WHERE is_active = 1 ORDER BY updated_at DESC"
        )
        return [self._row_to_session(r) for r in rows]

    async def list_all(
        self,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
        search: str | None = None,
        state_filter: str | None = None,
    ) -> list[Session]:
        conditions = []
        params: list = []
        if not include_archived:
            conditions.append("is_active = 1")
        if state_filter:
            conditions.append("state = ?")
            params.append(state_filter)
        if search:
            conditions.append("title LIKE ?")
            params.append(f"%{search}%")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = await self.db.fetch_all(
            f"SELECT * FROM sessions {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return [self._row_to_session(r) for r in rows]

    async def get_summaries(
        self,
        limit: int = 10,
        include_archived: bool = False,
    ) -> list[dict]:
        conditions = []
        if not include_archived:
            conditions.append("is_active = 1")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = await self.db.fetch_all(
            f"""SELECT id, title, mode, state, provider, model, message_count, total_tokens, total_cost,
                       context_percent, created_at, updated_at, is_active, error_count, last_error, parent_session_id
                FROM sessions {where} ORDER BY updated_at DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in rows]

    async def update(self, session: Session) -> Session:
        session.updated_at = datetime.now()
        plan_approved = session.plan_approved_at.isoformat() if session.plan_approved_at else None
        exported_at = session.exported_at.isoformat() if session.exported_at else None
        await self.db.execute(
            """UPDATE sessions SET title=?, mode=?, state=?, updated_at=?, is_active=?, metadata_json=?,
               parent_session_id=?, plan_output=?, plan_approved_at=?, message_count=?, total_tokens=?,
               total_cost=?, model=?, provider=?, agent_state=?, context_used=?, context_window=?,
               context_percent=?, error_count=?, last_error=?, export_format=?, exported_at=?
               WHERE id=?""",
            (
                session.title,
                session.mode.value if hasattr(session.mode, 'value') else session.mode,
                session.state.value if hasattr(session.state, 'value') else session.state,
                session.updated_at.isoformat(),
                int(session.is_active),
                json.dumps(session.metadata),
                session.parent_session_id,
                session.plan_output,
                plan_approved,
                session.message_count,
                session.total_tokens,
                session.total_cost,
                session.model,
                session.provider,
                session.agent_state,
                session.context_used,
                session.context_window,
                session.context_percent,
                session.error_count,
                session.last_error,
                session.export_format,
                exported_at,
                session.id,
            ),
        )
        await self.db.commit()
        return session

    async def find_latest_with_plan(self) -> Session | None:
        row = await self.db.fetch_one(
            "SELECT * FROM sessions WHERE plan_output != '' AND is_active = 1 ORDER BY updated_at DESC LIMIT 1"
        )
        if not row:
            return None
        plan_approved = datetime.fromisoformat(row["plan_approved_at"]) if row.get("plan_approved_at") else None
        return Session(
            id=row["id"],
            title=row["title"],
            mode=row["mode"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            workspace_root=row["workspace_root"],
            is_active=bool(row["is_active"]),
            metadata=json.loads(row["metadata_json"]),
            parent_session_id=row.get("parent_session_id"),
            state=row.get("state", "created"),
            plan_output=row.get("plan_output", ""),
            plan_approved_at=plan_approved,
        )

    async def delete(self, session_id: str) -> bool:
        await self.db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await self.db.commit()
        return True


class MessageRepository:
    def __init__(self, db: Database):
        self.db = db
        self._blob_store = BlobStore.from_db_path(db.db_path)

    async def create(self, message: Message) -> Message:
        packed_events = [self._blob_store.pack(e.model_dump()) for e in message.events]
        events_json = json.dumps(packed_events)
        await self.db.execute(
            "INSERT INTO messages (id, session_id, role, content, events_json, token_count, created_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                message.id,
                message.session_id,
                message.role,
                message.content,
                events_json,
                message.token_count,
                message.created_at.isoformat(),
                json.dumps(message.metadata),
            ),
        )
        await self.db.commit()
        return message

    async def get_by_session(self, session_id: str, limit: int = 50) -> list[Message]:
        rows = await self.db.fetch_all(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        )
        messages = []
        for r in reversed(rows):
            events_data = json.loads(r["events_json"])
            events = [Event(**self._blob_store.unpack(e)) for e in events_data]
            messages.append(
                Message(
                    id=r["id"],
                    session_id=r["session_id"],
                    role=r["role"],
                    content=r["content"],
                    events=events,
                    token_count=r["token_count"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                    metadata=json.loads(r["metadata_json"]),
                )
            )
        return messages

    async def count_tokens(self, session_id: str) -> int:
        row = await self.db.fetch_one(
            "SELECT COALESCE(SUM(token_count), 0) as total FROM messages WHERE session_id = ?",
            (session_id,),
        )
        return row["total"] if row else 0


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

    async def ensure_seeded(self) -> None:
        """Seed default providers and model catalog into SQLite if providers table is empty."""
        count_row = await self.db.fetch_one("SELECT COUNT(*) as cnt FROM providers")
        if count_row and count_row["cnt"] > 0:
            return

        catalog = load_catalog()
        seed_providers = _seed_providers_from_catalog(catalog)
        default_provider = catalog.get("default_active_provider", "nvidia")

        now = datetime.now().isoformat()
        for p in seed_providers:
            await self.db.execute(
                """
                INSERT INTO providers (id, name, description, api_key, model, base_url, max_tokens, temperature, is_active, swatch_json, adapter_type, capabilities_json, api_key_prefix, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p["id"],
                    p["name"],
                    p.get("description", ""),
                    "",
                    p["model"],
                    p["base_url"],
                    4096,
                    0.7,
                    p["is_active"],
                    json.dumps(p["swatch"]),
                    p["adapter"],
                    json.dumps(p["capabilities"]),
                    p["api_key_prefix"],
                    now,
                ),
            )
            for m in p["models"]:
                await self.db.execute(
                    """
                    INSERT INTO provider_models (id, provider_id, name, context_window, description, is_default)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        m["id"],
                        p["id"],
                        m["name"],
                        m.get("context_window", 128000),
                        m.get("description", ""),
                        m.get("is_default", 0),
                    ),
                )
        await self.db.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('active_provider', ?)",
            (default_provider,),
        )
        await self.db.commit()

    async def get_active_provider_id(self) -> str:
        row = await self.db.fetch_one("SELECT value FROM app_settings WHERE key = 'active_provider'")
        if row and row["value"]:
            return row["value"]
        active_row = await self.db.fetch_one("SELECT id FROM providers WHERE is_active = 1 LIMIT 1")
        if active_row:
            return active_row["id"]
        return "nvidia"

    async def set_active_provider_id(self, provider_id: str) -> None:
        await self.db.execute("UPDATE providers SET is_active = 0")
        await self.db.execute("UPDATE providers SET is_active = 1 WHERE id = ?", (provider_id,))
        await self.db.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('active_provider', ?)",
            (provider_id,),
        )
        await self.db.commit()

    async def get_provider(self, provider_id: str) -> dict | None:
        await self.ensure_seeded()
        row = await self.db.fetch_one("SELECT * FROM providers WHERE id = ?", (provider_id,))
        if not row:
            return None
        p = dict(row)
        models_rows = await self.db.fetch_all(
            "SELECT id, name, context_window, description, is_default FROM provider_models WHERE provider_id = ?",
            (provider_id,),
        )
        p["models"] = [dict(m) for m in models_rows]
        p["swatch"] = json.loads(p.get("swatch_json", "[]"))
        return p

    async def list_providers(self) -> dict[str, dict]:
        await self.ensure_seeded()
        rows = await self.db.fetch_all("SELECT * FROM providers")
        providers = {}
        for r in rows:
            pid = r["id"]
            p = dict(r)
            models_rows = await self.db.fetch_all(
                "SELECT id, name, context_window, description, is_default FROM provider_models WHERE provider_id = ?",
                (pid,),
            )
            p["models"] = [dict(m) for m in models_rows]
            p["swatch"] = json.loads(p.get("swatch_json", "[]"))
            providers[pid] = p
        return providers

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
        existing = await self.db.fetch_one("SELECT * FROM providers WHERE id = ?", (provider_id,))

        if existing:
            new_key = api_key if api_key.strip() else existing["api_key"]
            new_model = model if model.strip() else existing["model"]
            new_base = base_url if base_url.strip() else existing["base_url"]

            await self.db.execute(
                """
                UPDATE providers
                SET api_key = ?, model = ?, base_url = ?, max_tokens = ?, temperature = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_key, new_model, new_base, max_tokens, temperature, now, provider_id),
            )
        else:
            await self.db.execute(
                """
                INSERT INTO providers (id, name, description, api_key, model, base_url, max_tokens, temperature, is_active, swatch_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?)
                """,
                (provider_id, provider_id.title(), "", api_key, model, base_url, max_tokens, temperature, 0, now),
            )

        if set_active:
            await self.set_active_provider_id(provider_id)
        else:
            await self.db.commit()

    async def get_models_for_provider(self, provider_id: str) -> list[dict]:
        await self.ensure_seeded()
        rows = await self.db.fetch_all(
            "SELECT id, name, context_window, description, is_default FROM provider_models WHERE provider_id = ?",
            (provider_id,),
        )
        return [dict(r) for r in rows]


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
        import uuid as _uid
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
        record_id = str(_uid.uuid4())
        await self.db.execute(
            "INSERT INTO token_usage (id, session_id, provider, model, prompt_tokens, completion_tokens, total_tokens, context_window, percent, created_at, cost_usd, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, step_index, estimated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record_id,
                session_id,
                provider,
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                context_window,
                round(percent, 3),
                _dt.now().isoformat(),
                cost_usd,
                input_tokens or prompt_tokens,
                output_tokens or completion_tokens,
                cache_read_tokens,
                cache_creation_tokens,
                step_index,
                1 if estimated else 0,
            ),
        )
        await self.db.commit()
        return record_id

    async def record_degradation(
        self, session_id: str, step_index: int, before_tokens: int, after_tokens: int, reason: str
    ) -> None:
        import uuid as _uid
        from datetime import datetime as _dt
        await self.db.execute(
            "INSERT INTO context_degradation (id, session_id, step_index, before_tokens, after_tokens, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(_uid.uuid4()), session_id, step_index, before_tokens, after_tokens, reason, _dt.now().isoformat()),
        )
        await self.db.commit()

    async def seed_pricing(self) -> None:
        from datetime import datetime as _dt
        try:
            catalog = load_catalog()
            now = _dt.now().isoformat()
            for prov_id, prov_data in catalog.get("providers", {}).items():
                for m in prov_data.get("models", []):
                    p = m.get("pricing", {})
                    await self.db.execute(
                        """INSERT OR REPLACE INTO pricing (model_id, provider, input_1m, output_1m, cache_read_1m, cache_creation_1m, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (m["id"], prov_id, p.get("input", 0.0), p.get("output", 0.0),
                         p.get("cache_read", 0.0), p.get("cache_creation", 0.0), now),
                    )
            await self.db.commit()
        except Exception:
            pass

    async def get_stats_by_model(self, since: str | None = None, until: str | None = None) -> list[dict]:
        where = ""
        params: list = []
        if since:
            where += " AND created_at >= ?"
            params.append(since)
        if until:
            where += " AND created_at <= ?"
            params.append(until)
        rows = await self.db.fetch_all(f"""
            SELECT
                provider,
                model,
                COUNT(*) as request_count,
                COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) as total_completion_tokens,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(SUM(cost_usd), 0) as total_cost_usd,
                COALESCE(SUM(cache_read_tokens), 0) as total_cache_read,
                COALESCE(SUM(cache_creation_tokens), 0) as total_cache_creation,
                MAX(context_window) as context_window
            FROM token_usage
            WHERE step_index = -1{where}
            GROUP BY provider, model
            ORDER BY total_tokens DESC
        """, params)
        return [dict(r) for r in rows] if rows else []

    async def get_total_stats(self, since: str | None = None, until: str | None = None) -> dict:
        where = ""
        params: list = []
        if since:
            where += " AND created_at >= ?"
            params.append(since)
        if until:
            where += " AND created_at <= ?"
            params.append(until)
        row = await self.db.fetch_one(f"""
            SELECT
                COUNT(*) as total_requests,
                COALESCE(SUM(total_tokens), 0) as grand_total_tokens,
                COALESCE(SUM(input_tokens), 0) as grand_total_input,
                COALESCE(SUM(output_tokens), 0) as grand_total_output,
                COALESCE(SUM(prompt_tokens), 0) as grand_total_prompt,
                COALESCE(SUM(completion_tokens), 0) as grand_total_completion,
                COALESCE(SUM(cost_usd), 0) as grand_total_cost_usd,
                COALESCE(SUM(cache_read_tokens), 0) as grand_total_cache_read,
                COALESCE(SUM(cache_creation_tokens), 0) as grand_total_cache_creation,
                COUNT(DISTINCT provider || ':' || model) as unique_models
            FROM token_usage
            WHERE step_index = -1{where}
        """, params)
        return dict(row) if row else {}

    async def get_cost_summary(self, period: str = "all") -> list[dict]:
        from datetime import datetime as _dt
        now = _dt.now()
        since = None
        if period == "day":
            since = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif period == "week":
            since = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            from datetime import timedelta
            since = (now - timedelta(days=7)).isoformat()
        elif period == "month":
            since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        rows = await self.db.fetch_all(f"""
            SELECT
                provider, model,
                COUNT(*) as requests,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(SUM(cost_usd), 0) as total_cost,
                COALESCE(SUM(input_tokens), 0) as total_input,
                COALESCE(SUM(output_tokens), 0) as total_output
            FROM token_usage
            WHERE step_index = -1{' AND created_at >= ?' if since else ''}
            GROUP BY provider, model
            ORDER BY total_cost DESC
        """, [since] if since else [])
        return [dict(r) for r in rows] if rows else []

    async def get_budget_status(self, session_id: str) -> dict:
        row = await self.db.fetch_one(
            "SELECT * FROM budget_settings WHERE session_id = ? AND active = 1 ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        )
        if not row:
            return {"active": False, "max_session_cost": 0, "max_daily_cost": 0, "max_monthly_cost": 0}
        settings = dict(row)
        from datetime import datetime as _dt
        now = _dt.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        session_cost = await self.db.fetch_one(
            "SELECT COALESCE(SUM(cost_usd), 0) as total FROM token_usage WHERE session_id = ?", (session_id,)
        )
        daily_cost = await self.db.fetch_one(
            "SELECT COALESCE(SUM(cost_usd), 0) as total FROM token_usage WHERE session_id = ? AND created_at >= ?",
            (session_id, today_start),
        )
        monthly_cost = await self.db.fetch_one(
            "SELECT COALESCE(SUM(cost_usd), 0) as total FROM token_usage WHERE session_id = ? AND created_at >= ?",
            (session_id, month_start),
        )
        return {
            "active": True,
            "max_session_cost": settings.get("max_session_cost", 0),
            "max_daily_cost": settings.get("max_daily_cost", 0),
            "max_monthly_cost": settings.get("max_monthly_cost", 0),
            "session_cost": dict(session_cost).get("total", 0) if session_cost else 0,
            "daily_cost": dict(daily_cost).get("total", 0) if daily_cost else 0,
            "monthly_cost": dict(monthly_cost).get("total", 0) if monthly_cost else 0,
        }

    async def upsert_budget(self, session_id: str, max_session_cost: float, max_daily_cost: float, max_monthly_cost: float, active: bool = True) -> None:
        import uuid as _uid
        from datetime import datetime as _dt
        now = _dt.now().isoformat()
        record_id = str(_uid.uuid4())
        await self.db.execute(
            "INSERT INTO budget_settings (id, session_id, max_session_cost, max_daily_cost, max_monthly_cost, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (record_id, session_id, max_session_cost, max_daily_cost, max_monthly_cost, int(active), now, now),
        )
        await self.db.commit()

    async def get_per_step_stats(self, session_id: str) -> list[dict]:
        rows = await self.db.fetch_all(
            "SELECT * FROM token_usage WHERE session_id = ? AND step_index >= 0 ORDER BY step_index ASC",
            (session_id,),
        )
        return [dict(r) for r in rows] if rows else []

    async def get_efficiency(self, session_id: str) -> dict:
        total_row = await self.db.fetch_one(
            "SELECT COALESCE(SUM(total_tokens), 0) as total_consumed, COALESCE(SUM(cost_usd), 0) as total_cost FROM token_usage WHERE session_id = ?",
            (session_id,),
        )
        final_row = await self.db.fetch_one(
            "SELECT total_tokens as final_context FROM token_usage WHERE session_id = ? AND step_index = -1 ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        )
        deg_rows = await self.db.fetch_all(
            "SELECT COUNT(*) as count, COALESCE(SUM(before_tokens - after_tokens), 0) as waste FROM context_degradation WHERE session_id = ?",
            (session_id,),
        )
        total_consumed = dict(total_row).get("total_consumed", 0) if total_row else 0
        total_cost = dict(total_row).get("total_cost", 0) if total_row else 0
        final_context = dict(final_row).get("final_context", 0) if final_row else 0
        deg = dict(deg_rows[0]) if deg_rows else {"count": 0, "waste": 0}
        waste_ratio = (deg["waste"] / total_consumed) if total_consumed > 0 else 0.0
        return {
            "total_tokens_consumed": total_consumed,
            "total_cost_usd": total_cost,
            "final_context_used": final_context,
            "waste_ratio": round(waste_ratio, 4),
            "summarization_count": deg["count"],
            "average_context_utilization": round(final_context / total_consumed, 4) if total_consumed > 0 else 0.0,
        }

    async def get_session_token_usage(self, session_id: str) -> list[dict]:
        rows = await self.db.fetch_all(
            "SELECT * FROM token_usage WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        return [dict(r) for r in rows] if rows else []

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
        await self.db.execute(
            """INSERT INTO token_usage (id, session_id, provider, model, prompt_tokens, completion_tokens, total_tokens, context_window, percent, created_at, cost_usd, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, cache_write_tokens, reasoning_tokens, step_index, estimated, is_retry, retry_of, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record_id,
                session_id,
                provider,
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                context_window,
                round(percent, 3),
                datetime.now().isoformat(),
                cost_usd,
                input_tokens or prompt_tokens,
                output_tokens or completion_tokens,
                cache_read_tokens,
                cache_creation_tokens,
                cache_write_tokens,
                reasoning_tokens,
                step_index,
                1 if estimated else 0,
                1 if is_retry else 0,
                retry_of,
                duration_ms,
            ),
        )
        await self.db.commit()
        return record_id

    async def get_lifetime_stats(self) -> dict:
        row = await self.db.fetch_one("""
            SELECT
                COUNT(*) as total_requests,
                COALESCE(SUM(total_tokens), 0) as grand_total_tokens,
                COALESCE(SUM(cost_usd), 0) as grand_total_cost,
                COALESCE(SUM(input_tokens), 0) as grand_total_input,
                COALESCE(SUM(output_tokens), 0) as grand_total_output,
                COALESCE(SUM(cache_read_tokens), 0) as grand_total_cache_read,
                COALESCE(SUM(cache_creation_tokens), 0) as grand_total_cache_write,
                COALESCE(SUM(reasoning_tokens), 0) as grand_total_reasoning,
                COUNT(DISTINCT session_id) as total_sessions
            FROM token_usage
        """)
        return dict(row) if row else {}


class CheckpointRepository:
    def __init__(self, db: Database):
        self.db = db

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
        await self.db.execute(
            "INSERT INTO session_checkpoints (id, session_id, checkpoint_type, step_index, snapshot_data, token_count, message_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, session_id, checkpoint_type, step_index, json.dumps(snapshot_data or {}), token_count, message_count, datetime.now().isoformat()),
        )
        await self.db.commit()
        return cid

    async def get_latest(self, session_id: str) -> dict | None:
        row = await self.db.fetch_one(
            "SELECT * FROM session_checkpoints WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        )
        if row:
            result = dict(row)
            result["snapshot_data"] = json.loads(result["snapshot_data"])
            return result
        return None

    async def list_by_session(self, session_id: str, limit: int = 20) -> list[dict]:
        rows = await self.db.fetch_all(
            "SELECT * FROM session_checkpoints WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        )
        result = []
        for r in rows:
            d = dict(r)
            d["snapshot_data"] = json.loads(d["snapshot_data"])
            result.append(d)
        return result

    async def delete_old(self, session_id: str, keep: int = 5) -> int:
        rows = await self.db.fetch_all(
            "SELECT id FROM session_checkpoints WHERE session_id = ? ORDER BY created_at DESC LIMIT -1 OFFSET ?",
            (session_id, keep),
        )
        if not rows:
            return 0
        ids = [r["id"] for r in rows]
        placeholders = ",".join("?" for _ in ids)
        await self.db.execute(f"DELETE FROM session_checkpoints WHERE id IN ({placeholders})", ids)
        await self.db.commit()
        return len(ids)


class SyncEventRepository:
    def __init__(self, db: Database):
        self.db = db
        self._blob_store = BlobStore.from_db_path(db.db_path)

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
        await self.db.execute(
            "INSERT INTO sync_events (id, session_id, event_type, event_data, sequence, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (eid, session_id, event_type, json.dumps(self._blob_store.pack(event_data)), seq, created_at or datetime.now().isoformat()),
        )
        await self.db.commit()
        return eid

    async def _next_sequence(self, session_id: str) -> int:
        row = await self.db.fetch_one(
            "SELECT COALESCE(MAX(sequence), 0) as max_seq FROM sync_events WHERE session_id = ?",
            (session_id,),
        )
        return (row["max_seq"] if row else 0) + 1

    async def get_since(self, session_id: str, sequence: int = 0) -> list[dict]:
        rows = await self.db.fetch_all(
            "SELECT * FROM sync_events WHERE session_id = ? AND sequence > ? ORDER BY sequence ASC",
            (session_id, sequence),
        )
        result = []
        for r in rows:
            d = dict(r)
            d["event_data"] = self._blob_store.unpack(json.loads(d["event_data"]))
            result.append(d)
        return result

    async def get_latest_sequence(self, session_id: str) -> int:
        row = await self.db.fetch_one(
            "SELECT COALESCE(MAX(sequence), 0) as max_seq FROM sync_events WHERE session_id = ?",
            (session_id,),
        )
        return row["max_seq"] if row else 0

    async def delete_by_session(self, session_id: str) -> None:
        await self.db.execute("DELETE FROM sync_events WHERE session_id = ?", (session_id,))
        await self.db.commit()


class SessionStatusHistoryRepository:
    def __init__(self, db: Database):
        self.db = db

    async def record(self, session_id: str, from_state: str | None, to_state: str, reason: str = "") -> str:
        hid = str(_uuid.uuid4())
        await self.db.execute(
            "INSERT INTO session_status_history (id, session_id, from_state, to_state, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (hid, session_id, from_state, to_state, reason, datetime.now().isoformat()),
        )
        await self.db.commit()
        return hid

    async def get_history(self, session_id: str, limit: int = 50) -> list[dict]:
        rows = await self.db.fetch_all(
            "SELECT * FROM session_status_history WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        )
        return [dict(r) for r in rows]


class DraftRepository:
    def __init__(self, db: Database):
        self.db = db

    async def save(self, session_id: str, prompt: str = "", context: dict | None = None, ttl_hours: int = 24) -> str:
        did = str(_uuid.uuid4())
        expires = (datetime.now() + timedelta(hours=ttl_hours)).isoformat()
        await self.db.execute(
            "INSERT INTO session_drafts (id, session_id, prompt, context, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (did, session_id, prompt, json.dumps(context or {}), expires, datetime.now().isoformat()),
        )
        await self.db.commit()
        return did

    async def get_by_session(self, session_id: str) -> dict | None:
        row = await self.db.fetch_one(
            "SELECT * FROM session_drafts WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        )
        if row:
            result = dict(row)
            result["context"] = json.loads(result["context"])
            return result
        return None

    async def list_expired(self) -> list[dict]:
        rows = await self.db.fetch_all(
            "SELECT * FROM session_drafts WHERE expires_at < ?",
            (datetime.now().isoformat(),),
        )
        return [dict(r) for r in rows]

    async def delete_expired(self) -> int:
        rows = await self.list_expired()
        if not rows:
            return 0
        ids = [r["id"] for r in rows]
        placeholders = ",".join("?" for _ in ids)
        await self.db.execute(f"DELETE FROM session_drafts WHERE id IN ({placeholders})", ids)
        await self.db.commit()
        return len(ids)

