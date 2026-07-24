import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .connection import Database
from zenith.core.session import Session
from zenith.core.message import Message
from zenith.core.events import Event

CATALOG_PATH = Path(__file__).parent.parent / "config" / "provider_catalog.json"


def load_catalog() -> dict:
    """Load the provider catalog from the canonical JSON file."""
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class SessionRepository:
    def __init__(self, db: Database):
        self.db = db

    async def create(self, session: Session) -> Session:
        await self.db.execute(
            "INSERT INTO sessions (id, title, mode, created_at, updated_at, workspace_root, is_active, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session.id,
                session.title,
                session.mode,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
                session.workspace_root,
                int(session.is_active),
                json.dumps(session.metadata),
            ),
        )
        await self.db.commit()
        return session

    async def get(self, session_id: str) -> Optional[Session]:
        row = await self.db.fetch_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
        if not row:
            return None
        return Session(
            id=row["id"],
            title=row["title"],
            mode=row["mode"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            workspace_root=row["workspace_root"],
            is_active=bool(row["is_active"]),
            metadata=json.loads(row["metadata_json"]),
        )

    async def list_active(self) -> list[Session]:
        rows = await self.db.fetch_all(
            "SELECT * FROM sessions WHERE is_active = 1 ORDER BY updated_at DESC"
        )
        return [
            Session(
                id=r["id"],
                title=r["title"],
                mode=r["mode"],
                created_at=datetime.fromisoformat(r["created_at"]),
                updated_at=datetime.fromisoformat(r["updated_at"]),
                workspace_root=r["workspace_root"],
                is_active=bool(r["is_active"]),
                metadata=json.loads(r["metadata_json"]),
            )
            for r in rows
        ]

    async def update(self, session: Session) -> Session:
        session.updated_at = datetime.now()
        await self.db.execute(
            "UPDATE sessions SET title=?, mode=?, updated_at=?, is_active=?, metadata_json=? WHERE id=?",
            (
                session.title,
                session.mode,
                session.updated_at.isoformat(),
                int(session.is_active),
                json.dumps(session.metadata),
                session.id,
            ),
        )
        await self.db.commit()
        return session

    async def delete(self, session_id: str) -> bool:
        await self.db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await self.db.commit()
        return True


class MessageRepository:
    def __init__(self, db: Database):
        self.db = db

    async def create(self, message: Message) -> Message:
        events_json = json.dumps([e.model_dump() for e in message.events])
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
            events = [Event(**e) for e in events_data]
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

