"""Async running-summary scheduler (todo 3.13-3.14).

Schedules one weak-model summary per completed turn, **non-blocking**: the turn
returns as soon as the background task is scheduled; the LLM call happens after
the fact. On completion the fresh summary is written back to the session
metadata, so the next prompt prefers it and falls back to the last persisted one
while a write is still pending.

Ordering: per session we keep a monotonic generation counter. A turn that
finishes schedules generation ``++counter``. A background task applies its
summary only if its generation is still the latest — a stale summary that
arrives late (because a newer turn was scheduled while it was in flight) is
dropped, so freshness is preserved without locks. Background LLM calls are
serialized so they never interleave with a streaming turn on the shared
provider.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from server.agents.summarizer import ConversationSummarizer
from server.config.constants import RUNNING_SUMMARY_MESSAGE_LIMIT

if TYPE_CHECKING:
    from server.config.settings import AppSettings
    from server.providers.base import BaseProvider
    from server.storage.session_store import FileMessageRepository, FileSessionRepository

logger = logging.getLogger(__name__)


class RunningSummaryScheduler:
    def __init__(
        self,
        config: AppSettings,
        provider: BaseProvider,
        session_repo: FileSessionRepository,
        message_repo: FileMessageRepository,
    ) -> None:
        self._config = config
        self._provider = provider
        self._session_repo = session_repo
        self._message_repo = message_repo
        self._generations: dict[str, int] = {}
        # Latest scheduled task per session (superseded tasks stay in
        # _inflight until they finish — dropping them here would let them
        # escape drain() while still holding the DB/provider open).
        self._tasks: dict[str, asyncio.Task] = {}
        self._inflight: set[asyncio.Task] = set()
        self._serialize = asyncio.Lock()

    def schedule(self, session_id: str) -> None:
        """Schedule a background running summary for a completed turn.

        A no-op when the async summary is disabled. Called from a running event
        loop (the turn's completion path), so the task is created immediately
        and the turn never awaits the LLM call.
        """
        if not getattr(self._config, "async_summary_enabled", False):
            return
        generation = self._generations.get(session_id, 0) + 1
        self._generations[session_id] = generation
        task = asyncio.get_running_loop().create_task(self._run(session_id, generation))
        self._tasks[session_id] = task
        self._inflight.add(task)
        task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task: asyncio.Task) -> None:
        self._inflight.discard(task)
        for sid, current in list(self._tasks.items()):
            if current is task:
                self._tasks.pop(sid, None)

    async def drain(self) -> None:
        """Await all in-flight background summaries (test seam).

        A completed turn schedules the summary fire-and-forget, so tests must
        drain before teardown or the background task can still hold the DB open.
        Includes superseded tasks that were replaced by a newer schedule().
        """
        pending = [t for t in self._inflight if not t.done()]
        for task in pending:
            try:
                await task
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Async running summary drain failed: %s", e)

    async def _run(self, session_id: str, generation: int) -> None:
        try:
            if self._generations.get(session_id) != generation:
                return  # superseded before this task started
            messages = await self._message_repo.get_by_session(
                session_id, limit=RUNNING_SUMMARY_MESSAGE_LIMIT
            )
            if not messages:
                return
            session = await self._session_repo.get(session_id)
            if session is None:
                return
            previous = ((session.metadata or {}).get("summary") or "").strip() or None
            model = str(getattr(self._provider, "model", "") or "")
            async with self._serialize:
                summary = await ConversationSummarizer(self._config, self._provider).summarize(
                    messages, model, session_id=session_id, previous_summary=previous
                )
            if not summary:
                return
            if self._generations.get(session_id) != generation:
                return  # a newer turn superseded this summary while it ran
            session.metadata["summary"] = summary
            await self._session_repo.update(session)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Async running summary failed for %s: %s", session_id, e)
