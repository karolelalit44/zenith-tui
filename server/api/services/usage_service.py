"""Usage application service.

Owns the read-side token-usage view exposed over the API. Routes in
``server/api/server.py`` depend on this service instead of reaching into the
WebSocket transport internals (``ZenithHandler.handlers.usage_repo``) for
persistence.

Flow: route → UsageService → FileTokenUsageRepository → storage.

The service centralizes the HTTP-facing shapes and consistent empty/error
handling so each route stays thin. It is dependency-injected with the usage
repository for testability.
"""

from __future__ import annotations

import logging

from server.storage.usage_store import FileTokenUsageRepository

logger = logging.getLogger(__name__)


class UsageService:
    def __init__(self, repo: FileTokenUsageRepository):
        self._repo = repo

    async def get_token_stats(self, since: str | None = None, until: str | None = None) -> dict:
        try:
            models = await self._repo.get_stats_by_model(since=since, until=until)
            totals = await self._repo.get_total_stats(since=since, until=until)
            return {"models": models, "totals": totals}
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Failed to fetch token stats: %s", e)
            return {"models": [], "totals": {}}

    async def get_cost_summary(self, period: str = "all") -> dict:
        try:
            data = await self._repo.get_cost_summary(period=period)
            return {"data": data}
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Failed to fetch cost summary: %s", e)
            return {"data": []}

    async def get_steps(self, session_id: str) -> dict:
        try:
            steps = await self._repo.get_per_step_stats(session_id)
            return {"steps": steps}
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Failed to fetch step stats: %s", e)
            return {"steps": []}

    async def get_efficiency(self, session_id: str) -> dict:
        try:
            return await self._repo.get_efficiency(session_id)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Failed to fetch efficiency: %s", e)
            return {}
