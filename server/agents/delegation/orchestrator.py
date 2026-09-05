"""Captain orchestrator: capability-routed delegation of specialist missions.

Owns the full delegation pathway for one investigation:

1. duplicate detection via the Repository Intelligence Cache;
2. lifecycle orchestration events (thinking -> delegating -> working ->
    complete) plus raw ``crewmate_spawned``/``crewmate_status``/``crewmate_complete``/
    ``crewmate_failed`` kinds alongside;
3. an isolated child session per mission;
4. a bounded run (timeout, context budget, read-only guard);
5. structured ``AgentResult`` assembly, persistence and caching;
6. one final ``success`` event built from the result — the scenario terminal.

Guardrails (spec): depth <= MAX_DELEGATION_DEPTH, one child per run,
AGENT_TIMEOUT_SECONDS per agent, CREWMATE_CONTEXT_BUDGET_TOKENS context cap.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from server.config.settings import AppSettings
from server.domain.events import Event, EventKind
from server.domain.message import Message
from server.providers import responder as r
from server.providers.base import BaseProvider
from server.toolkit.registry import ToolRegistry

from .agent_definition import AgentDefinition
from .agent_result import AgentResult
from .scout import (
    ACTIVITY_MAX_CHARS,
    CrewmateRun,
    assemble_result,
    register_crewmate_guard,
    run_crewmate,
)
from .task_envelope import AgentTask, build_task_envelope, task_signature

logger = logging.getLogger(__name__)

MAX_DELEGATION_DEPTH = 1
MAX_CHILDREN_PER_RUN = 1
# Routed missions get the 'deep' budget: free/mini models reason slowly, and
# the 2026-08-26 incident showed 120s cancelling real investigations.
AGENT_TIMEOUT_SECONDS = 150
CREWMATE_CONTEXT_BUDGET_TOKENS = 64_000
DELEGATION_CACHE_TTL_SECONDS = 300
WORKING_EVENT_CAP = 3

# AgentResult.status -> TUI CrewmateStatus
CREWMATE_STATUS_BY_RESULT = {
    "completed": "completed",
    "failed": "failed",
    "timed_out": "failed",
    "cancelled": "retired",
    "cached": "completed",
}


class RepositoryIntelligenceCache:
    """In-memory signature -> AgentResult store that survives turns."""

    def __init__(self, ttl_seconds: float = DELEGATION_CACHE_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._store: dict[str, tuple[AgentResult, float]] = {}

    def get(self, signature: str) -> AgentResult | None:
        entry = self._store.get(signature)
        if entry is None:
            return None
        result, cached_at = entry
        age = datetime.now(UTC).timestamp() - cached_at
        if age > self._ttl_seconds:
            del self._store[signature]
            return None
        # Copy on read: callers must never mutate shared cached intelligence.
        return result.model_copy(deep=True)

    def put(self, signature: str, result: AgentResult) -> None:
        self._store[signature] = (
            result,
            datetime.now(UTC).timestamp(),
        )

    def clear(self) -> None:
        self._store.clear()


def _timeline_entry(message: str, entry_type: str = "info") -> dict:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "message": message[:ACTIVITY_MAX_CHARS],
        "type": entry_type,
    }


class CaptainOrchestrator:
    def __init__(
        self,
        config: AppSettings,
        provider: BaseProvider,
        tool_registry: ToolRegistry,
        session_repo=None,
        message_repo=None,
        compaction_service=None,
        cache: RepositoryIntelligenceCache | None = None,
    ) -> None:
        self._config = config
        self._provider = provider
        self._tool_registry = tool_registry
        self._session_repo = session_repo
        self._message_repo = message_repo
        self._compaction_service = compaction_service
        self.cache = cache or RepositoryIntelligenceCache()
        self.last_result: AgentResult | None = None
        self.children_spawned = 0
        self._in_flight = False

    # ------------------------------------------------------------------ #
    # event builders                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _orchestration_event(
        session_id: str,
        stage: str,
        captain_message: str,
        *,
        plan: list[dict] | None = None,
        crewmates: list[dict] | None = None,
        timeline: list[dict] | None = None,
        active_step: str | None = None,
    ) -> Event:
        data: dict = {"stage": stage, "captainMessage": captain_message}
        if plan:
            data["plan"] = plan
        if crewmates:
            data["crewmates"] = crewmates
        if timeline:
            data["timeline"] = timeline
        if active_step:
            data["activeStep"] = active_step
        return Event(kind=EventKind.CAPTAIN_ORCHESTRATION, data=data, session_id=session_id)

    @staticmethod
    def _crewmate(
        definition: AgentDefinition,
        task: AgentTask,
        status: str,
        *,
        activity: str | None = None,
        progress: int | None = None,
        result_summary: str | None = None,
        error: str | None = None,
    ) -> dict:
        payload: dict = {
            "id": f"{definition.id}:{task.task_id[:8]}",
            "name": definition.name,
            "role": definition.role,
            "task": task.objective[:ACTIVITY_MAX_CHARS],
            "status": status,
        }
        if activity:
            payload["activity"] = activity[:ACTIVITY_MAX_CHARS]
        if progress is not None:
            payload["progress"] = progress
        if result_summary:
            payload["resultSummary"] = result_summary[:ACTIVITY_MAX_CHARS]
        if error:
            payload["error"] = error[:ACTIVITY_MAX_CHARS]
        return payload

    def _spawned_event(self, definition: AgentDefinition, task: AgentTask) -> Event:
        return Event(
            kind=EventKind.CREWMATE_SPAWNED,
            data={
                "crewmate_id": definition.id,
                "name": definition.name,
                "role": definition.role,
                "task_id": task.task_id,
                "capability": task.capability,
                "parent_session_id": task.session_id,
                "model": getattr(self._provider, "model", "") or "",
            },
            session_id=task.session_id,
        )

    @staticmethod
    def _status_event(agent_id: str, status: str, activity: str, progress: int) -> Event:
        return Event(
            kind=EventKind.CREWMATE_STATUS,
            data={
                "crewmate_id": agent_id,
                "status": status,
                "activity": activity[:ACTIVITY_MAX_CHARS],
                "progress": progress,
            },
        )

    # ------------------------------------------------------------------ #
    # delegation pathway                                                  #
    # ------------------------------------------------------------------ #

    async def investigate(
        self,
        content: str,
        definition: AgentDefinition,
        parent_session_id: str,
        history: list[Message] | None = None,
        parent_task_id: str | None = None,
        depth: int = 0,
        *,
        timeout_seconds: int | None = None,
        max_context_tokens: int | None = None,
    ) -> AsyncIterator[Event]:
        """Run one delegated mission; yield lifecycle + forwarded events.

        ``timeout_seconds`` / ``max_context_tokens`` let the explore tool
        apply its per-thoroughness budgets (WP5 Phase 2) without touching the
        routed-mission defaults. ``None`` keeps the module-level default so
        tests can still monkeypatch ``AGENT_TIMEOUT_SECONDS``.
        """
        resolved_timeout = timeout_seconds if timeout_seconds is not None else AGENT_TIMEOUT_SECONDS
        if self._in_flight or depth >= MAX_DELEGATION_DEPTH:
            blocked = AgentResult(
                task_id=f"{definition.id}-blocked",
                agent_id=definition.id,
                status="failed",
                summary="",
                error=(
                    f"Delegation refused: max depth {MAX_DELEGATION_DEPTH} "
                    "or concurrent mission in flight."
                ),
            )
            self.last_result = blocked
            yield r.error(blocked.error or "Delegation refused", parent_session_id)
            return

        task = build_task_envelope(
            objective=content,
            definition=definition,
            session_id=parent_session_id,
            max_context_tokens=min(
                self._config.max_context_tokens,
                max_context_tokens or CREWMATE_CONTEXT_BUDGET_TOKENS,
            ),
            context_digest=self._context_digest(history),
            parent_task_id=parent_task_id,
            depth=depth + 1,
        )
        crewmate_id = f"{definition.id}:{task.task_id[:8]}"

        # ---- duplicate detection --------------------------------------- #
        signature = task_signature(content, definition.id, parent_session_id)
        cached = self.cache.get(signature)
        if cached is not None:
            result = cached.model_copy(deep=True)
            result.task_id = task.task_id
            result.status = "cached"
            self.last_result = result
            yield self._orchestration_event(
                parent_session_id,
                "complete",
                content,
                plan=[
                    {
                        "id": task.task_id[:8],
                        "title": content[:ACTIVITY_MAX_CHARS],
                        "assignedCrewmate": crewmate_id,
                        "status": "completed",
                    }
                ],
                crewmates=[
                    self._crewmate(
                        definition,
                        task,
                        CREWMATE_STATUS_BY_RESULT[result.status],
                        progress=100,
                        result_summary=result.summary,
                    )
                ],
                timeline=[_timeline_entry("Cached intelligence reused — no re-run", "info")],
                active_step="complete",
            )
            yield Event(
                kind=EventKind.CREWMATE_COMPLETE,
                data={
                    "crewmate_id": definition.id,
                    "task_id": task.task_id,
                    "result_summary": result.summary[:ACTIVITY_MAX_CHARS],
                    "status": result.status,
                },
                session_id=parent_session_id,
            )
            yield r.success(
                result.summary,
                parent_session_id,
                iterations=result.metrics.iterations,
                token_info={"used": result.metrics.tokens_used},
                elapsed_ms=result.metrics.elapsed_ms or None,
            )
            return

        # Structural guarantee of MAX_CHILDREN_PER_RUN: exactly one child
        # session is created per run, below, and crewmate max_crewmates == 0.
        self._in_flight = True
        self.children_spawned = 0
        try:
            # ---- thinking ------------------------------------------------ #
            timeline: list[dict] = [_timeline_entry(f"Objective received: {content}", "info")]
            yield self._orchestration_event(
                parent_session_id,
                "thinking",
                content,
                timeline=list(timeline),
                active_step="thinking",
            )

            # ---- delegating ---------------------------------------------- #
            plan_item = {
                "id": task.task_id[:8],
                "title": content[:ACTIVITY_MAX_CHARS],
                "assignedAgent": crewmate_id,
                "status": "in_progress",
                "details": definition.description[:ACTIVITY_MAX_CHARS],
            }
            crewmate = self._crewmate(definition, task, "assigned", progress=0)
            yield self._orchestration_event(
                parent_session_id,
                "delegating",
                content,
                plan=[plan_item],
                crewmates=[crewmate],
                timeline=list(timeline),
                active_step="delegating",
            )
            yield self._spawned_event(definition, task)

            # ---- child session ------------------------------------------- #
            child_session_id = await self._create_child_session(parent_session_id)
            task.child_session_id = child_session_id
            self.children_spawned += 1
            register_crewmate_guard(self._tool_registry)

            # ---- working ------------------------------------------------- #
            run = CrewmateRun()
            child_events: list[Event] = []
            working_emitted = 0
            last_activity = ""
            timed_out = False
            try:
                async with asyncio.timeout(resolved_timeout):
                    async for child_event in run_crewmate(
                        config=self._config,
                        provider=self._provider,
                        tool_registry=self._tool_registry,
                        compaction_service=self._compaction_service,
                        task=task,
                        definition=definition,
                        run=run,
                    ):
                        child_events.append(child_event)
                        yield child_event
                        activity = self._activity_from(child_event)
                        if not activity or activity == last_activity:
                            continue
                        last_activity = activity
                        if working_emitted >= WORKING_EVENT_CAP:
                            continue
                        working_emitted += 1
                        crewmate = self._crewmate(
                            definition,
                            task,
                            "working",
                            activity=activity,
                            progress=50,
                        )
                        timeline.append(_timeline_entry(activity))
                        yield self._status_event(definition.id, "working", activity, 50)
                        yield self._orchestration_event(
                            parent_session_id,
                            "working",
                            content,
                            plan=[plan_item],
                            crewmates=[crewmate],
                            timeline=list(timeline),
                            active_step=activity,
                        )
            except TimeoutError:
                timed_out = True
            except asyncio.CancelledError:
                # Mark, then re-raise: the executor's cancellation path owns
                # the interrupt warning and terminal semantics.
                self.last_result = AgentResult(
                    task_id=task.task_id,
                    agent_id=definition.id,
                    status="cancelled",
                    summary="",
                    metrics=_metrics_from(run),
                    error="Cancelled by user.",
                )
                raise

            # ---- assemble ------------------------------------------------ #
            if timed_out:
                result = assemble_result(
                    task,
                    definition,
                    run,
                    status="timed_out",
                    error=f"Investigation exceeded {resolved_timeout}s timeout.",
                )
                # Timeout salvage (WP6 hotfix): the outer cancel kills the
                # child before its own salvage can fire, which used to leave
                # the parent with an empty summary. One tools-free call turns
                # the gathered evidence into a real answer.
                salvaged = await self._salvage_child_summary(
                    provider=self._provider,
                    child_events=child_events,
                    objective=content,
                )
                if salvaged:
                    result.summary = salvaged
                    result.unverified = [
                        (
                            "Mission hit the time budget mid-investigation; "
                            "summary above is best-effort from gathered evidence."
                        )
                    ] + list(result.unverified)
            elif run.last_error:
                result = assemble_result(
                    task,
                    definition,
                    run,
                    status="failed",
                    error=run.last_error,
                )
            else:
                result = assemble_result(task, definition, run)
            self.last_result = result

            # ---- persist ------------------------------------------------- #
            await self._persist(parent_session_id, child_session_id, result, child_events)

            # ---- cache --------------------------------------------------- #
            self.cache.put(signature, result.model_copy(update={"status": "completed"}))

            # ---- complete ------------------------------------------------ #
            crewmate_status = CREWMATE_STATUS_BY_RESULT.get(result.status, "failed")
            ok = result.status == "completed"
            plan_item["status"] = "completed" if ok else "failed"
            final_crewmate = self._crewmate(
                definition,
                task,
                crewmate_status,
                progress=100 if ok else 0,
                result_summary=result.summary if ok else None,
                error=result.error if not ok else None,
            )
            timeline.append(
                _timeline_entry(
                    result.summary or result.error or "Mission ended",
                    "success" if ok else "warning",
                )
            )
            if ok:
                yield Event(
                    kind=EventKind.CREWMATE_COMPLETE,
                    data={
                        "crewmate_id": definition.id,
                        "task_id": task.task_id,
                        "result_summary": result.summary[:ACTIVITY_MAX_CHARS],
                        "status": result.status,
                    },
                    session_id=parent_session_id,
                )
            else:
                yield Event(
                    kind=EventKind.CREWMATE_FAILED,
                    data={
                        "crewmate_id": definition.id,
                        "task_id": task.task_id,
                        "error": (result.error or result.summary)[:ACTIVITY_MAX_CHARS],
                    },
                    session_id=parent_session_id,
                )
            yield self._orchestration_event(
                parent_session_id,
                "complete",
                content,
                plan=[plan_item],
                crewmates=[final_crewmate],
                timeline=timeline,
                active_step="complete",
            )
            yield r.success(
                result.summary,
                parent_session_id,
                iterations=result.metrics.iterations,
                token_info={"used": result.metrics.tokens_used},
                elapsed_ms=result.metrics.elapsed_ms or None,
            )
        finally:
            self._in_flight = False

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _salvage_child_summary(
        *, provider: BaseProvider, child_events: list[Event], objective: str
    ) -> str:
        """One tools-free completion over the child's gathered evidence.

        Runs when a mission is cancelled by the outer timeout — the point
        where the child's own salvage pass cannot fire. Bounded and silent on
        failure; an empty return keeps the deterministic fallback.
        """
        evidence: list[str] = []
        for event in child_events:
            if event.kind == EventKind.TOOL_RESULT:
                out = str(event.data.get("output") or "")[:400]
                if out:
                    evidence.append(f"[{event.data.get('tool')}] {out}")
            elif event.kind == EventKind.MESSAGE and not event.data.get("partial"):
                text = str(event.data.get("text") or "")[:400]
                if text:
                    evidence.append(f"[notes] {text}")
            if sum(len(e) for e in evidence) > 12_000:
                break
        if not evidence:
            return ""
        prompt = (
            "A delegated investigation was cut off by its time budget. Using "
            "ONLY the gathered evidence below, write the final report for this "
            f"objective: {objective}\n"
            "Be concrete (file paths, symbols). State what remains unknown.\n\n"
            + "\n".join(evidence)
        )
        try:
            async with asyncio.timeout(25):
                raw = await provider.complete([{"role": "user", "content": prompt}])
        except Exception as e:
            logger.warning("Timeout salvage completion failed: %s", e)
            return ""
        text = (raw or "").strip()
        return text if len(text) >= 40 else ""

    async def _create_child_session(self, parent_id: str) -> str:
        """Isolated child session (CrewmateLoop pattern)."""
        if not self._session_repo:
            import uuid

            return str(uuid.uuid4())
        try:
            parent = await self._session_repo.get(parent_id)
            if not parent:
                import uuid

                return str(uuid.uuid4())
            from server.domain.session import Session

            child = Session(
                title=f"crewmate-{parent.title}",
                mode=parent.mode,
                parent_session_id=parent_id,
                workspace_root=parent.workspace_root,
                provider=parent.provider,
                model=parent.model,
            )
            created = await self._session_repo.create(child)
            parent.add_child(created.id)
            await self._session_repo.update(parent)
            logger.info(
                "Crewmate child session %s -> %s (parent %s)",
                created.id,
                child.title,
                parent_id,
            )
            return created.id
        except Exception as exc:
            logger.warning("Failed to create crewmate child session: %s", exc)
            import uuid

            return str(uuid.uuid4())

    async def _persist(
        self,
        parent_session_id: str,
        child_session_id: str,
        result: AgentResult,
        child_events: list[Event],
    ) -> None:
        """Child assistant message + parent counters (CrewmateLoop.run pattern)."""
        try:
            if self._message_repo:
                assistant_msg = Message(
                    session_id=child_session_id,
                    role="assistant",
                    content=result.summary or "",
                    events=list(child_events),
                )
                await self._message_repo.create(assistant_msg)
        except Exception:
            logger.exception("Failed to persist crewmate child message")
        try:
            if self._session_repo:
                parent = await self._session_repo.get(parent_session_id)
                if parent:
                    parent.total_tokens += result.metrics.tokens_used
                    parent.message_count += 1
                    await self._session_repo.update(parent)
        except Exception:
            logger.warning("Failed to update parent token totals after crewmate run")

    @staticmethod
    def _activity_from(event: Event) -> str:
        kind = event.kind
        data = event.data
        if kind == EventKind.TOOL_CALL:
            params = data.get("params") or {}
            target = params.get("path") or params.get("pattern") or ""
            return f"tool {data.get('tool')}" + (f": {target}" if target else "")
        if kind == EventKind.TOOL_RESULT:
            state = "ok" if data.get("success") else "failed"
            return f"{data.get('tool')} {state}"
        if kind == EventKind.MESSAGE and not data.get("partial"):
            return (data.get("text") or "").strip()
        if kind == EventKind.THINKING:
            return (data.get("text") or "").strip()
        return ""

    @staticmethod
    def _context_digest(history: list[Message] | None) -> str:
        if not history:
            return ""
        recent = history[-3:]
        lines = []
        for msg in recent:
            role = getattr(msg, "role", "?")
            text = (getattr(msg, "content", "") or "").strip()
            if text:
                lines.append(f"{role}: {text[:300]}")
        return "\n".join(lines)


def _metrics_from(run: CrewmateRun):
    from .agent_result import AgentMetrics

    return AgentMetrics(
        tokens_used=int((run.token_info or {}).get("used") or 0),
        iterations=run.iterations,
        elapsed_ms=run.elapsed_ms,
        tool_calls=run.tool_calls,
    )
