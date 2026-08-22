from __future__ import annotations

import uuid as _uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..connection import Database
from ..models import (
    BudgetSettingsRecord,
    ContextDegradationRecord,
    PricingRecord,
    TokenUsageRecord,
)
from ..safe import safe_db
from .base import load_catalog


class TokenUsageRepository:
    def __init__(self, db: Database):
        self.db = db
        self._price_cache: dict[str, dict] | None = None

    def _resolve_price(self, provider: str, model: str) -> dict:
        if self._price_cache is None:
            self._price_cache = {}
            try:
                catalog = load_catalog(self.db.db_path)
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
        context_occupancy: int = 0,
    ) -> str:
        from datetime import datetime as _dt

        # QA-10: occupancy is the composed-context snapshot; total_tokens is the
        # provider-billed run usage. When occupancy is unknown (legacy callers /
        # pre-QA-10 rows) fall back to total_tokens so percent stays meaningful.
        occupancy = context_occupancy if context_occupancy > 0 else total_tokens
        percent = occupancy / context_window * 100 if context_window > 0 else 0.0
        price = self._resolve_price(provider, model)
        if estimated:
            cost_usd = 0.0
        else:
            input_cost = (input_tokens or prompt_tokens) * price["input"] / 1000000
            output_cost = (output_tokens or completion_tokens) * price["output"] / 1000000
            cache_read_cost = (cache_read_tokens or 0) * price.get("cache_read", 0) / 1000000
            cache_creation_cost = (
                (cache_creation_tokens or 0) * price.get("cache_creation", 0) / 1000000
            )
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
                    context_occupancy=context_occupancy,
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
            catalog = load_catalog(self.db.db_path)
            now = _dt.now().isoformat()
            async with self.db.session() as s:
                for prov_id, prov_data in catalog.get("providers", {}).items():
                    for m in prov_data.get("models", []):
                        p = m.get("pricing", {})
                        await s.execute(
                            sqlite_insert(PricingRecord)
                            .values(
                                model_id=m["id"],
                                provider=prov_id,
                                input_1m=p.get("input", 0.0),
                                output_1m=p.get("output", 0.0),
                                cache_read_1m=p.get("cache_read", 0.0),
                                cache_creation_1m=p.get("cache_creation", 0.0),
                                updated_at=now,
                            )
                            .on_conflict_do_update(
                                index_elements=["provider", "model_id"],
                                set_={
                                    "input_1m": sqlite_insert(PricingRecord).excluded.input_1m,
                                    "output_1m": sqlite_insert(PricingRecord).excluded.output_1m,
                                    "cache_read_1m": sqlite_insert(
                                        PricingRecord
                                    ).excluded.cache_read_1m,
                                    "cache_creation_1m": sqlite_insert(
                                        PricingRecord
                                    ).excluded.cache_creation_1m,
                                    "updated_at": sqlite_insert(PricingRecord).excluded.updated_at,
                                },
                            )
                        )
                await s.commit()
        except Exception:
            pass

    @safe_db("token_stats", table="token_usage")
    async def get_stats_by_model(
        self, since: str | None = None, until: str | None = None
    ) -> list[dict]:
        stmt = (
            select(
                TokenUsageRecord.provider,
                TokenUsageRecord.model,
                func.count().label("request_count"),
                func.coalesce(func.sum(TokenUsageRecord.input_tokens), 0).label(
                    "total_input_tokens"
                ),
                func.coalesce(func.sum(TokenUsageRecord.output_tokens), 0).label(
                    "total_output_tokens"
                ),
                func.coalesce(func.sum(TokenUsageRecord.prompt_tokens), 0).label(
                    "total_prompt_tokens"
                ),
                func.coalesce(func.sum(TokenUsageRecord.completion_tokens), 0).label(
                    "total_completion_tokens"
                ),
                func.coalesce(func.sum(TokenUsageRecord.total_tokens), 0).label("total_tokens"),
                func.coalesce(func.sum(TokenUsageRecord.cost_usd), 0).label("total_cost_usd"),
                func.coalesce(func.sum(TokenUsageRecord.cache_read_tokens), 0).label(
                    "total_cache_read"
                ),
                func.coalesce(func.sum(TokenUsageRecord.cache_creation_tokens), 0).label(
                    "total_cache_creation"
                ),
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
            func.coalesce(func.sum(TokenUsageRecord.completion_tokens), 0).label(
                "grand_total_completion"
            ),
            func.coalesce(func.sum(TokenUsageRecord.cost_usd), 0).label("grand_total_cost_usd"),
            func.coalesce(func.sum(TokenUsageRecord.cache_read_tokens), 0).label(
                "grand_total_cache_read"
            ),
            func.coalesce(func.sum(TokenUsageRecord.cache_creation_tokens), 0).label(
                "grand_total_cache_creation"
            ),
            func.count(
                func.distinct(TokenUsageRecord.provider + ":" + TokenUsageRecord.model)
            ).label("unique_models"),
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
                    .where(
                        BudgetSettingsRecord.session_id == session_id,
                        BudgetSettingsRecord.active.is_(True),
                    )
                    .order_by(BudgetSettingsRecord.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not rec:
                return {
                    "active": False,
                    "max_session_cost": 0,
                    "max_daily_cost": 0,
                    "max_monthly_cost": 0,
                }
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
    async def upsert_budget(
        self,
        session_id: str,
        max_session_cost: float,
        max_daily_cost: float,
        max_monthly_cost: float,
        active: bool = True,
    ) -> None:
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
                (
                    await s.execute(
                        select(TokenUsageRecord)
                        .where(
                            TokenUsageRecord.session_id == session_id,
                            TokenUsageRecord.step_index >= 0,
                        )
                        .order_by(TokenUsageRecord.step_index.asc())
                    )
                )
                .scalars()
                .all()
            )
            return [self._record_to_dict(r) for r in rows]

    def _record_to_dict(self, r: TokenUsageRecord) -> dict:
        return {c.name: getattr(r, c.name) for c in TokenUsageRecord.__table__.columns}

    @safe_db("get_efficiency", table="token_usage")
    async def get_efficiency(self, session_id: str) -> dict:
        async with self.db.session() as s:
            total_row = (
                (
                    await s.execute(
                        select(
                            func.coalesce(func.sum(TokenUsageRecord.total_tokens), 0).label(
                                "total_consumed"
                            ),
                            func.coalesce(func.sum(TokenUsageRecord.cost_usd), 0).label(
                                "total_cost"
                            ),
                        ).where(TokenUsageRecord.session_id == session_id)
                    )
                )
                .mappings()
                .one()
            )
            final_row = (
                (
                    await s.execute(
                        select(
                            # QA-10: final_context is the composed OCCUPANCY at the
                            # last recorded turn; fall back to the billed total for
                            # legacy rows recorded before occupancy existed.
                            func.coalesce(
                                func.nullif(TokenUsageRecord.context_occupancy, 0),
                                TokenUsageRecord.total_tokens,
                            ).label("final_context")
                        )
                        .where(
                            TokenUsageRecord.session_id == session_id,
                            TokenUsageRecord.step_index == -1,
                        )
                        .order_by(TokenUsageRecord.created_at.desc())
                        .limit(1)
                    )
                )
                .mappings()
                .first()
            )
            deg_rows = (
                (
                    await s.execute(
                        select(
                            func.count().label("count"),
                            func.coalesce(
                                func.sum(
                                    ContextDegradationRecord.before_tokens
                                    - ContextDegradationRecord.after_tokens
                                ),
                                0,
                            ).label("waste"),
                        ).where(ContextDegradationRecord.session_id == session_id)
                    )
                )
                .mappings()
                .one()
            )
        total_consumed = int(total_row["total_consumed"] or 0)
        total_cost = float(total_row["total_cost"] or 0)
        final_context = int(final_row["final_context"] or 0) if final_row else 0
        deg = dict(deg_rows)
        waste_ratio = deg["waste"] / total_consumed if total_consumed > 0 else 0.0
        return {
            "total_tokens_consumed": total_consumed,
            "total_cost_usd": total_cost,
            "final_context_used": final_context,
            "waste_ratio": round(waste_ratio, 4),
            "summarization_count": deg["count"],
            "average_context_utilization": round(final_context / total_consumed, 4)
            if total_consumed > 0
            else 0.0,
        }
