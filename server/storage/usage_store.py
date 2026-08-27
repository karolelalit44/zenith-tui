"""File-backed per-session token usage records.

Replaces the usage half of ``TokenUsageRepository`` (token_usage /
pricing tables). Per-session rows live in ``sessions/<id>.usage.jsonl``.
Pricing resolves from ``models.json`` directly, so the separate pricing
table/seed step disappears (decision D15).

Context-degradation diagnostics were removed entirely (decision D12):
``record_degradation`` no longer exists and efficiency stats report zero
waste.
"""

from __future__ import annotations

import asyncio
import uuid as _uuid
from datetime import datetime, timedelta
from typing import Any

from .atomic import append_jsonl_sync, read_json, read_jsonl
from .paths import StorageHome
from .session_file import iter_session_files, locate

_ZERO_PRICE = {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_creation": 0.0}


class FileTokenUsageRepository:
    def __init__(self, home: StorageHome):
        self.home = home
        self._price_cache: dict[str, dict] | None = None
        self._price_cache_stamp: int | None = None

    # ── pricing ───────────────────────────────────────────────────────
    def _catalog_stamp(self) -> int | None:
        try:
            return self.home.models_path.stat().st_mtime_ns
        except OSError:
            return None

    def _resolve_price(self, provider: str, model: str) -> dict:
        stamp = self._catalog_stamp()
        if self._price_cache is None or stamp != self._price_cache_stamp:
            cache: dict[str, dict] = {}
            try:
                doc = read_json(self.home.models_path, None) or {}
                for entry in (doc.get("models") or {}).values():
                    p = entry.get("pricing") or {}
                    key = f"{entry.get('providerId')}:{entry.get('id')}"
                    cache[key] = {
                        "input": float(p.get("input", 0.0)),
                        "output": float(p.get("output", 0.0)),
                        "cache_read": float(p.get("cache_read", 0.0)),
                        "cache_creation": float(p.get("cache_creation", 0.0)),
                    }
            except Exception:
                cache = {}
            self._price_cache = cache
            self._price_cache_stamp = stamp
        lookup = f"{provider}:{model}"
        if lookup in self._price_cache:
            return self._price_cache[lookup]
        for key, val in self._price_cache.items():
            if key.endswith(f":{model}"):
                return val
        return dict(_ZERO_PRICE)

    # ── recording ─────────────────────────────────────────────────────
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
        occupancy = context_occupancy if context_occupancy > 0 else total_tokens
        percent = occupancy / context_window * 100 if context_window > 0 else 0.0
        price = self._resolve_price(provider, model)
        if estimated:
            cost_usd = 0.0
        else:
            in_tok = input_tokens or prompt_tokens
            out_tok = output_tokens or completion_tokens
            cost_usd = round(
                in_tok * price["input"] / 1_000_000
                + out_tok * price["output"] / 1_000_000
                + cache_read_tokens * price.get("cache_read", 0.0) / 1_000_000
                + cache_creation_tokens * price.get("cache_creation", 0.0) / 1_000_000,
                6,
            )
        record_id = str(_uuid.uuid4())
        line = {
            "id": record_id,
            "session_id": session_id,
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "context_window": context_window,
            "percent": round(percent, 3),
            "created_at": datetime.now().isoformat(),
            "cost_usd": cost_usd,
            "input_tokens": input_tokens or prompt_tokens,
            "output_tokens": output_tokens or completion_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "step_index": step_index,
            "estimated": estimated,
            "context_occupancy": context_occupancy,
        }
        async with self.home.lock:
            append_jsonl_sync(
                locate(self.home, session_id),  # type: ignore[arg-type]
                {"t": "usage", **line},
            )
        return record_id

    # ── aggregation ───────────────────────────────────────────────────
    def _iter_all(self, since: str | None = None, until: str | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in iter_session_files(self.home):
            for rec in read_jsonl(path):
                if rec.get("t") != "usage":
                    continue
                created = str(rec.get("created_at", ""))
                if since and created < since:
                    continue
                if until and created > until:
                    continue
                out.append(rec)
        return out

    @staticmethod
    def _sum(rows: list[dict], key: str) -> float:
        return sum(float(r.get(key, 0) or 0) for r in rows)

    async def get_stats_by_model(
        self, since: str | None = None, until: str | None = None
    ) -> list[dict]:
        all_rows = await asyncio.to_thread(self._iter_all, since, until)
        rows = [r for r in all_rows if r.get("step_index") == -1]
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for r in rows:
            grouped.setdefault((str(r.get("provider")), str(r.get("model"))), []).append(dict(r))
        result: list[dict[str, Any]] = []
        for (provider, model), grp in grouped.items():
            result.append(
                {
                    "provider": provider,
                    "model": model,
                    "request_count": len(grp),
                    "total_input_tokens": int(self._sum(grp, "input_tokens")),
                    "total_output_tokens": int(self._sum(grp, "output_tokens")),
                    "total_prompt_tokens": int(self._sum(grp, "prompt_tokens")),
                    "total_completion_tokens": int(self._sum(grp, "completion_tokens")),
                    "total_tokens": int(self._sum(grp, "total_tokens")),
                    "total_cost_usd": self._sum(grp, "cost_usd"),
                    "total_cache_read": int(self._sum(grp, "cache_read_tokens")),
                    "total_cache_creation": int(self._sum(grp, "cache_creation_tokens")),
                    "context_window": max(
                        (int(r.get("context_window", 0)) for r in grp), default=0
                    ),
                }
            )
        result.sort(key=lambda r: int(r["total_tokens"]), reverse=True)
        return result

    async def get_total_stats(self, since: str | None = None, until: str | None = None) -> dict:
        all_rows = await asyncio.to_thread(self._iter_all, since, until)
        rows = [r for r in all_rows if r.get("step_index") == -1]
        models = {f"{r.get('provider')}:{r.get('model')}" for r in rows}
        return {
            "total_requests": len(rows),
            "grand_total_tokens": int(self._sum(rows, "total_tokens")),
            "grand_total_input": int(self._sum(rows, "input_tokens")),
            "grand_total_output": int(self._sum(rows, "output_tokens")),
            "grand_total_prompt": int(self._sum(rows, "prompt_tokens")),
            "grand_total_completion": int(self._sum(rows, "completion_tokens")),
            "grand_total_cost_usd": self._sum(rows, "cost_usd"),
            "grand_total_cache_read": int(self._sum(rows, "cache_read_tokens")),
            "grand_total_cache_creation": int(self._sum(rows, "cache_creation_tokens")),
            "unique_models": len(models),
        }

    async def get_cost_summary(self, period: str = "all") -> list[dict]:
        now = datetime.now()
        since: str | None = None
        if period == "day":
            since = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif period == "week":
            since = (now - timedelta(days=7)).isoformat()
        elif period == "month":
            since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        all_rows = await asyncio.to_thread(self._iter_all, since)
        rows = [dict(r) for r in all_rows if r.get("step_index") == -1]
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for r in rows:
            grouped.setdefault((str(r.get("provider")), str(r.get("model"))), []).append(dict(r))
        result: list[dict[str, Any]] = [
            {
                "provider": provider,
                "model": model,
                "requests": len(grp),
                "total_tokens": int(self._sum(grp, "total_tokens")),
                "total_cost": self._sum(grp, "cost_usd"),
                "total_input": int(self._sum(grp, "input_tokens")),
                "total_output": int(self._sum(grp, "output_tokens")),
            }
            for (provider, model), grp in grouped.items()
        ]
        result.sort(key=lambda r: float(r["total_cost"]), reverse=True)
        return result

    def _usage_rows_sync(self, session_id: str) -> list[dict]:
        path = locate(self.home, session_id)
        if path is None:
            return []
        return [dict(r) for r in read_jsonl(path) if r.get("t") == "usage"]

    async def get_per_step_stats(self, session_id: str) -> list[dict]:
        all_rows = await asyncio.to_thread(self._usage_rows_sync, session_id)
        rows = [r for r in all_rows if int(r.get("step_index", -1)) >= 0]
        rows.sort(key=lambda r: int(r.get("step_index", 0)))
        return rows

    async def get_efficiency(self, session_id: str) -> dict:
        rows = await asyncio.to_thread(self._usage_rows_sync, session_id)
        total_consumed = int(sum(float(r.get("total_tokens", 0) or 0) for r in rows))
        total_cost = sum(float(r.get("cost_usd", 0) or 0) for r in rows)
        finals = [r for r in rows if r.get("step_index") == -1]
        final_context = 0
        if finals:
            last = max(finals, key=lambda r: str(r.get("created_at", "")))
            final_context = int(last.get("context_occupancy") or last.get("total_tokens") or 0)
        return {
            "total_tokens_consumed": total_consumed,
            "total_cost_usd": total_cost,
            "final_context_used": final_context,
            "waste_ratio": 0.0,
            "summarization_count": 0,
            "average_context_utilization": round(final_context / total_consumed, 4)
            if total_consumed > 0
            else 0.0,
        }
