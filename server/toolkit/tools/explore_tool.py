"""WP5 Phase 1 — model-invocable explore delegation.

``ExploreTool ("explore")`` lets the main agent dispatch a focused, read-only
investigation to a crewmate (the defined **Pathfinder** explorer, or a custom
crewmate built from runtime parameters) without pulling the child's
intermediate tool output into the parent context.

Contract highlights:
- Governance: ``config.explore_delegation`` gates availability (D3).
- Budgets: per-mission timeout/context tokens by thoroughness (Phase 2) plus
  a rolling-window aggregate token ledger across children (D6).
- Isolation: only the rendered structured report crosses the boundary (S2);
  child transcript events are consumed, never forwarded. The captain-level
  delegation lifecycle (captain_orchestration stages + crewmate_spawned /
  status / complete / failed) IS forwarded in order — it is the operationally
  meaningful story of the mission and feeds the TUI's orchestration card.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from typing import Any

from server.agents.delegation.agent_definition import (
    AgentDefinition,
    build_apogee_definition,
    build_custom_definition,
)
from server.agents.delegation.orchestrator import CaptainOrchestrator
from server.config.constants import (
    APPOGEE_AGENT_NAME,
    APPOGEE_AGENT_ROLE,
    CONCURRENCY_GROUP_CREWMATE,
    COST_CLASS_HIGH,
    DEFAULT_EXPLORE_THOROUGHNESS,
    ENRICH_DELIVERABLE_VERBS,
    ENRICH_SKIP_MIN_CHARS,
    EXPLORE_BUDGET_WINDOW_SECONDS,
    EXPLORE_BUDGETS,
    EXPLORE_CUSTOM_NAME_MAX_CHARS,
    EXPLORE_PARALLEL_DEFAULT,
    EXPLORE_RESULT_MAX_CHARS,
    EXPLORE_THOROUGHNESS_LEVELS,
    LATENCY_CLASS_HIGH,
    RISK_MEDIUM,
    TOOL_DOMAIN_CREWMATE,
)
from server.config.environment import ZENITH_ENRICH_TIMEOUT, ZENITH_SALVAGE_TIMEOUT
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.toolkit.registry import current_tool_session_id

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Outer hard-cap sits at mission timeout + a salvage allowance. Once the
# crewmate's inner mission budget fires (orchestrator.investigate), a final
# provider completion (_salvage_child_summary, capped by ZENITH_SALVAGE_TIMEOUT)
# turns the gathered evidence into a report. The grace MUST cover that call —
# at 15s it always lost and the parent got a content-free "no result" instead of
# a timed-out report.
_EXPLORE_SALVAGE_GRACE_SECONDS = int(ZENITH_SALVAGE_TIMEOUT) + 30
# Additional slack folded into the TTFT-derived budget floor: two LLM legs
# (enrichment + crewmate turns) on the provider's measured latency, plus
# tool-execution time, must fit inside the mission wall clock.
_EXPLORE_TTFT_SLACK_S = 30
# Hard ceiling on the TTFT-derived floor so an anomalous measurement cannot
# stretch missions without bound.  Must exceed the highest static budget
# (deep=360s) so the floor is meaningful on slow providers.
_EXPLORE_TTFT_FLOOR_MAX_S = 420


class ExploreSpendLedger:
    """Rolling-window aggregate token guard across explore children (D6).

    Missions record their spend on completion; before spawning, callers ask
    :meth:`would_exceed` so an over-budget fan-out is refused up front and
    already-running missions finish naturally.
    """

    def __init__(self) -> None:
        self._spend: deque[tuple[float, int]] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - EXPLORE_BUDGET_WINDOW_SECONDS
        while self._spend and self._spend[0][0] < cutoff:
            self._spend.popleft()

    def window_total(self) -> int:
        self._prune(time.monotonic())
        return sum(tokens for _, tokens in self._spend)

    def would_exceed(self, budget_tokens: int) -> bool:
        return self.window_total() >= budget_tokens

    def record(self, tokens: int) -> None:
        if tokens > 0:
            self._spend.append((time.monotonic(), int(tokens)))


# One ledger per process: spend is global regardless of which registry
# instance dispatched the mission.
_ledger = ExploreSpendLedger()
# Width guard for environments that execute tools outside the parent loop.
_spawn_semaphore = asyncio.Semaphore(EXPLORE_PARALLEL_DEFAULT)

# Captain-level lifecycle kinds forwarded to the parent wire stream in order.
# Deliberately excludes the child transcript (thinking/message/tool_*/progress
# from the crewmate) — S2 isolation keeps the parent context clean.
_LIFECYCLE_KINDS = frozenset(
    {
        EventKind.CAPTAIN_ORCHESTRATION,
        EventKind.CREWMATE_SPAWNED,
        EventKind.CREWMATE_STATUS,
        EventKind.CREWMATE_COMPLETE,
        EventKind.CREWMATE_FAILED,
    }
)

# Bound on forwarded lifecycle entries: CREWMATE_STATUS can tick at high
# frequency; cap the list so ToolResult metadata / WS replay stays bounded.
# Terminal kinds (spawn/complete/failed + orchestration stages) are always
# kept — only the oldest STATUS entries are evicted when full.
_LIFECYCLE_MAX_EVENTS = 200


class ExploreTool(BaseTool):
    name = "explore"
    description = (
        "Delegate a focused read-only codebase investigation to an isolated "
        "crewmate (default: Apogee) that returns evidence-backed findings with "
        "confidence levels. Use for multi-file 'how does X work' questions. Do NOT "
        "use when the target file is known, one grep suffices, or the repo is tiny. "
        "Issue independent objectives as separate calls together; synthesize by theme."
    )
    capability_id = "crewmate"
    requires_mode = None
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_CREWMATE
    domains = (TOOL_DOMAIN_CREWMATE,)
    search_terms = (
        "explore",
        "investigate",
        "delegate",
        "crewmate",
        "apogee",
        "research",
        "find code",
    )
    risk_level = RISK_MEDIUM
    cost_class = COST_CLASS_HIGH
    latency_class = LATENCY_CLASS_HIGH

    def __init__(
        self,
        *,
        config: AppSettings | None = None,
        provider: Any | None = None,
        tool_registry: Any | None = None,
        weak_model: str | None = None,
    ) -> None:
        self._config = config
        self._provider = provider
        self._tool_registry = tool_registry
        # Hybrid routing (D2): quick/standard missions run on the cheap model
        # when one is configured; deep missions inherit the parent's model.
        self._weak_model = weak_model

    def get_schema(self) -> dict:
        crewmate_schema = {
            "type": "object",
            "description": (
                "Optional custom crewmate for this mission. Structural rules "
                "(read-only tools, no delegation) always apply."
            ),
            "properties": {
                "name": {"type": "string", "maxLength": EXPLORE_CUSTOM_NAME_MAX_CHARS},
                "role": {
                    "type": "string",
                    "description": "Specialty label, e.g. 'Persistence Analyst'",
                },
                "focus": {
                    "type": "string",
                    "description": "Extra scoped instructions for this crewmate",
                },
                "model": {
                    "type": "string",
                    "description": "Optional model override for this mission",
                },
            },
        }
        return {
            "type": "object",
            "properties": {
                "objective": {
                    "type": "string",
                    "description": (
                        "Task-shaped question with a clear deliverable, e.g. "
                        "'find where compaction is triggered and what threshold "
                        "gates it'. One focused objective per call."
                    ),
                },
                "scope": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional subdirectory hints, e.g. ['server/agents']",
                },
                "thoroughness": {
                    "type": "string",
                    "enum": list(EXPLORE_THOROUGHNESS_LEVELS),
                    "default": DEFAULT_EXPLORE_THOROUGHNESS,
                    "description": (
                        "quick=150s targeted lookup, standard=240s balanced, "
                        "deep=360s multi-subsystem sweep"
                    ),
                },
                "crewmate": crewmate_schema,
            },
            "required": ["objective"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        if self._config is None or self._provider is None:
            return ToolResult(success=False, error="Explore delegation is not configured")
        if self._config.explore_delegation == "off":
            return ToolResult(
                success=False,
                error="Explore delegation is disabled by configuration (explore_delegation='off').",
            )
        objective = str(params.get("objective") or "").strip()
        if not objective:
            return ToolResult(success=False, error="No objective provided")

        thoroughness = self._resolve_thoroughness(params.get("thoroughness"))
        budget = dict(EXPLORE_BUDGETS.get(thoroughness, EXPLORE_BUDGETS["standard"]))
        # Fit the mission wall clock to the provider's measured latency: on a slow
        # provider (TTFT 38-75s observed) the static quick=150s window let one
        # hung leg burn the whole mission before the first tool turn. Floor the
        # budget at 2 round trips + tool slack on the latest measured TTFT. This
        # stays bounded because FIX A ceilings the stream legs it is derived from.
        ttft_ms = getattr(self._provider, "_last_ttft_ms", None)
        if ttft_ms:
            floor_s = min(
                math.ceil(2 * (ttft_ms / 1000.0)) + _EXPLORE_TTFT_SLACK_S,
                _EXPLORE_TTFT_FLOOR_MAX_S,
            )
            if budget["timeout_s"] < floor_s:
                logger.info(
                    "Explore budget floor applied thoroughness=%s base=%ds floor=%ds ttft_ms=%d",
                    thoroughness,
                    budget["timeout_s"],
                    floor_s,
                    ttft_ms,
                )
                budget["timeout_s"] = floor_s

        # Cheap guards precede ANY spend — enrichment is a provider call, so it
        # only happens after the budget window accepts a new mission.
        if _ledger.would_exceed(self._config.explore_token_budget):
            return ToolResult(
                success=False,
                error=(
                    f"Explore token budget exhausted for this window "
                    f"({self._config.explore_token_budget} tokens across recent "
                    "missions). Synthesize what you have or continue next turn."
                ),
                metadata=self._metadata(thoroughness, status="budget_exhausted"),
            )
        objective = await self._maybe_enrich(objective)

        scope = [str(s) for s in params.get("scope") or [] if str(s).strip()]
        definition, scoped_focus = self._build_definition(params, thoroughness)

        mission_objective = objective
        if scope:
            mission_objective += f"\nInvestigate within: {', '.join(scope)}."
        if scoped_focus:
            mission_objective += f"\nCrewmate focus: {scoped_focus}"

        orchestrator = CaptainOrchestrator(
            self._config,
            self._provider,
            self._tool_registry,
            cache=None,
        )
        logger.info(
            "Explore mission start thoroughness=%s budget=%ds crewmate=%s model=%s objective_chars=%d",
            thoroughness,
            budget["timeout_s"],
            definition.name,
            definition.model_override or getattr(self._provider, "model", "?"),
            len(mission_objective),
        )
        started = time.monotonic()
        active_session_id = current_tool_session_id.get() or f"explore:{workspace_root}"
        last_orch_data: dict[str, Any] | None = None
        lifecycle: list[tuple[str, dict[str, Any]]] = []
        try:
            async with asyncio.timeout(budget["timeout_s"] + _EXPLORE_SALVAGE_GRACE_SECONDS):
                async with _spawn_semaphore:
                    async for _event in orchestrator.investigate(
                        mission_objective,
                        definition,
                        parent_session_id=active_session_id,
                        timeout_seconds=budget["timeout_s"],
                        max_context_tokens=budget["context_tokens"],
                    ):
                        if _event.kind in _LIFECYCLE_KINDS:
                            data = _event.data
                            snapshot = dict(data) if isinstance(data, dict) else {}
                            if len(lifecycle) >= _LIFECYCLE_MAX_EVENTS:
                                # Evict the oldest STATUS tick to make room; if
                                # none exists, drop the oldest entry so terminal
                                # kinds (spawn/complete/failed) are preserved.
                                for i, (k, _) in enumerate(lifecycle):
                                    if k == str(EventKind.CREWMATE_STATUS):
                                        del lifecycle[i]
                                        break
                                else:
                                    del lifecycle[0]
                            lifecycle.append((str(_event.kind), snapshot))
                        if _event.kind == EventKind.CAPTAIN_ORCHESTRATION and isinstance(_event.data, dict):
                            last_orch_data = dict(_event.data)
                        continue
        except TimeoutError:
            logger.warning("Explore mission hard-timeout (thoroughness=%s)", thoroughness)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Explore mission failed: %s", e)
            return ToolResult(
                success=False,
                # Even a crashed mission reports actionably — mirrors WP2/WP3
                # philosophy: never an empty, context-free failure.
                output=f"[explore] failed\nError: {e}",
                metadata=self._with_orchestration(
                    self._metadata(
                        thoroughness,
                        status="failed",
                        crewmate_name=definition.name,
                        crewmate_role=definition.role,
                    ),
                    lifecycle,
                    last_orch_data,
                ),
            )
        elapsed_ms = int((time.monotonic() - started) * 1000)

        result = orchestrator.last_result
        if result is None:
            return ToolResult(
                success=False,
                error=(
                    "Explore mission produced no result: the crewmate exhausted "
                    f"its {budget['timeout_s']}s {thoroughness} budget and no "
                    "AgentResult was assembled (salvage likely cancelled by the "
                    "outer hard-cap). See the server log for the child trace."
                ),
                metadata=self._with_orchestration(
                    self._metadata(
                        thoroughness, status="failed", crewmate_name=definition.name
                    ),
                    lifecycle,
                    last_orch_data,
                ),
            )
        _ledger.record(result.metrics.tokens_used)

        cached = result.status == "cached"
        ok = result.status in ("completed", "cached")
        meta = self._metadata(
            thoroughness,
            status=result.status,
            crewmate_name=definition.name,
            crewmate_role=definition.role,
            result=result,
            cached=cached,
            elapsed_ms=elapsed_ms or result.metrics.elapsed_ms,
        )
        meta = self._with_orchestration(meta, lifecycle, last_orch_data)
        return ToolResult(success=ok, output=self._render(result), metadata=meta)

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #

    def _should_enrich(self, objective: str) -> bool:
        """Deep Research instruction-builder pattern, deterministic gate (D-dec):
        enrich only short, vague objectives. Detailed briefs pass through."""
        if not self._weak_model or len(objective) >= ENRICH_SKIP_MIN_CHARS:
            return False
        lowered = objective.lower()
        return not any(v in lowered for v in ENRICH_DELIVERABLE_VERBS)

    async def _maybe_enrich(self, objective: str) -> str:
        if not self._should_enrich(objective) or self._provider is None:
            return objective
        prompt = (
            "Rewrite this codebase investigation objective into a precise research "
            "brief for a read-only crewmate: state the deliverable shape, the "
            "scope boundaries, and what evidence would answer it. Output ONLY the "
            f"brief.\nObjective: {objective}"
        )
        request = [{"role": "user", "content": prompt}]
        try:
            import inspect

            kwargs: dict[str, Any] = {}
            if (
                self._weak_model
                and "model" in inspect.signature(self._provider.complete).parameters
            ):
                kwargs["model"] = self._weak_model
            result = await asyncio.wait_for(
                self._provider.complete(request, **kwargs),
                timeout=ZENITH_ENRICH_TIMEOUT,
            )
        except Exception as e:
            logger.debug("Objective enrichment skipped (%s); using raw objective", e)
            return objective
        enriched = (result or "").strip()
        if not enriched or len(enriched) < 8:
            return objective
        logger.info("Explore objective enriched via weak model (%d chars)", len(enriched))
        return f"{objective}\nResearch brief: {enriched}"

    @staticmethod
    def _resolve_thoroughness(value: Any) -> str:
        text = str(value or "").strip().lower()
        return text if text in EXPLORE_THOROUGHNESS_LEVELS else DEFAULT_EXPLORE_THOROUGHNESS

    def _build_definition(
        self, params: dict[str, Any], thoroughness: str
    ) -> tuple[AgentDefinition, str]:
        """Apogee by default; custom crewmate from runtime params when given.

        Hybrid model routing (D2): cheap model for quick/standard, parent's
        model for deep — unless the custom crewmate pins its own model.
        """
        routed_model = None if thoroughness == "deep" else self._weak_model
        custom = params.get("crewmate")
        if isinstance(custom, dict) and any(
            custom.get(key) for key in ("name", "role", "focus", "model")
        ):
            return build_custom_definition(
                name=str(custom.get("name") or ""),
                role=str(custom.get("role") or ""),
                focus=str(custom.get("focus") or ""),
                model_override=str(custom.get("model")) if custom.get("model") else routed_model,
            )
        return build_apogee_definition(model_override=routed_model), ""

    @staticmethod
    def _with_orchestration(
        meta: dict,
        lifecycle: list[tuple[str, dict[str, Any]]],
        last_orch_data: dict[str, Any] | None,
    ) -> dict:
        """Attach the mission's captain-level lifecycle to tool metadata.

        ``orchestration_events`` carries the FULL ordered lifecycle so the
        executor can replay it on the wire; ``orchestration_event`` preserves
        the legacy single-last-snapshot key for any consumer that reads it.
        """
        if lifecycle:
            meta["orchestration_events"] = [
                {"kind": kind, "data": dict(data)} for kind, data in lifecycle
            ]
        if last_orch_data:
            meta["orchestration_event"] = dict(last_orch_data)
        return meta

    @staticmethod
    def _metadata(
        thoroughness: str,
        *,
        status: str = "started",
        crewmate_name: str = APPOGEE_AGENT_NAME,
        crewmate_role: str = APPOGEE_AGENT_ROLE,
        result: Any = None,
        cached: bool = False,
        elapsed_ms: int = 0,
    ) -> dict:
        meta: dict = {
            "explore_status": status,
            "thoroughness": thoroughness,
            "crewmate_name": crewmate_name,
            "crewmate_role": crewmate_role,
        }
        if cached:
            meta["cached"] = True
        if elapsed_ms:
            meta["duration_ms"] = elapsed_ms
        if result is not None:
            findings = list(getattr(result, "findings", []) or [])
            meta.update(
                {
                    "tokens_used": result.metrics.tokens_used,
                    "tool_calls": result.metrics.tool_calls,
                    "iterations": result.metrics.iterations,
                    "verified_count": sum(1 for f in findings if f.confidence == "verified"),
                    "proposed_count": sum(1 for f in findings if f.confidence == "proposed"),
                    "unverified_count": len(getattr(result, "unverified", []) or []),
                    "blocked_count": len(getattr(result, "blocked", []) or []),
                    "affected_files": list(getattr(result, "affected_files", []) or [])[:8],
                    "error": result.error or "",
                    "summary": (result.summary or "")[:600],
                }
            )
        return meta

    @staticmethod
    def _render(result: Any) -> str:
        """Bounded, structured report for the parent context (S2 <= ~2 KB)."""
        lines: list[str] = []
        status_label = "completed" if result.status in ("completed", "cached") else result.status
        lines.append(f"[explore] {status_label}")
        if result.summary:
            lines.append(f"Summary: {result.summary.strip()}")
        findings = list(result.findings or [])
        if findings:
            lines.append("Findings:")
            for finding in findings[:6]:
                lines.append(f" - [{finding.confidence}] {finding.claim.strip()}")
            hidden = len(findings) - 6
            if hidden > 0:
                lines.append(f" (+{hidden} more findings omitted)")
        affected = list(result.affected_files or [])
        if affected:
            lines.append("Affected files: " + ", ".join(affected[:6]))
        unverified = list(result.unverified or [])
        if unverified:
            lines.append("Unverified: " + "; ".join(u[:120] for u in unverified[:3]))
        blocked = list(result.blocked or [])
        if blocked:
            lines.append("Blocked: " + "; ".join(b[:120] for b in blocked[:3]))
        if result.error:
            lines.append(f"Error: {result.error}")
        report = "\n".join(lines).strip() or "(no findings)"
        if len(report) > EXPLORE_RESULT_MAX_CHARS:
            report = report[: EXPLORE_RESULT_MAX_CHARS - 3].rstrip() + "..."
        return report
