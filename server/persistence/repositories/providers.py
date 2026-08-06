from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from server.config.constants import DEFAULT_CONTEXT_WINDOW

from .base import _seed_providers_from_catalog, load_catalog
from ..connection import Database
from ..models import ProviderModelRecord, ProviderRecord
from ..safe import safe_db


class ProviderRepositoryDB:
    def __init__(self, db: Database):
        self.db = db

    @safe_db("ensure_seeded", table="providers")
    async def ensure_seeded(self) -> None:
        async with self.db.session() as s:
            catalog = load_catalog(self.db.db_path)
            seed_providers = _seed_providers_from_catalog(catalog)
            now = datetime.now().isoformat()
            existing = {
                pid: True for pid in (await s.execute(select(ProviderRecord.id))).scalars().all()
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
                        is_active=p["is_active"],
                        swatch_json=json.dumps(p["swatch"]),
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
                        sqlite_insert(ProviderModelRecord)
                        .values(
                            id=m["id"],
                            provider_id=p["id"],
                            name=m["name"],
                            context_window=m.get("context_window", DEFAULT_CONTEXT_WINDOW),
                            description=m.get("description", ""),
                            is_default=bool(m.get("is_default")),
                        )
                        .on_conflict_do_nothing(index_elements=["provider_id", "id"])
                    )
            for pid, provider in catalog.get("providers", {}).items():
                if provider.get("custom_flow"):
                    continue
                curated = {m["id"] for m in provider.get("models", [])}
                if not curated:
                    continue
                stored = (
                    (
                        await s.execute(
                            select(ProviderModelRecord.id).where(
                                ProviderModelRecord.provider_id == pid
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for mid in stored:
                    if mid not in curated:
                        await s.execute(
                            delete(ProviderModelRecord).where(
                                ProviderModelRecord.provider_id == pid,
                                ProviderModelRecord.id == mid,
                            )
                        )
            await s.commit()
