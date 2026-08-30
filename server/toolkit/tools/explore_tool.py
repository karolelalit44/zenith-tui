"""WP5 Phase 1 — model-invocable explore delegation.

``ExploreTool ("explore")`` lets the main agent dispatch a focused, read-only
investigation to a crewmate (the defined **Pathfinder** explorer, or a custom
crewmate built from runtime parameters) without pulling the child's
intermediate tool output into the parent context.

Contract highlights:
- Governance: ``config.explore_delegation`` gates availability (D3).
- Budgets: per-mission timeout/context tokens by thoroughness (Phase 2) plus
  a rolling-window aggregate token ledger across children (D6).
- Isolation: only the rendered structured report crosses the boundary
  (S2); child transcript events are consumed, never forwarded.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any

from server.agents.delegation.agent_definition import (
    AgentDefinition,
    build_custom_definition,
    build_apogee_definition,
)
from server.agents.delegation.orchestrator import CaptainOrchestrator
from server.config.constants import (
    CONCURRENCY_GROUP_CREWMATE,
    COST_CLASS_HIGH,
    DEFAULT_ENRICH_TIMEOUT_SECONDS,
    DEFAULT_EXPLORE_THOROUGHNESS,
    ENRICH_DELIVERABLE_VERBS,
    ENRICH_SKIP_MIN_CHARS,
    ENRICH_TIMEOUT_ENV,
    EXPLORE_BUDGET_WINDOW_SECONDS,
    EXPLORE_BUDGETS,
    EXPLORE_CUSTOM_NAME_MAX_CHARS,
    EXPLORE_PARALLEL_DEFAULT,
    EXPLORE_RESULT_MAX_CHARS,
    EXPLORE_THOROUGHNESS_LEVELS,
    LATENCY_CLASS_HIGH,
    APPOGEE_AGENT_NAME,
    APPOGEE_AGENT_ROLE,
    PERMISSION_CREWMATE,
    RISK_MEDIUM,
    TOOL_DOMAIN_CREWMATE,
)
from server.config.env import optional_float
from server.config.settings import AppSettings

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

_EXPLORE_DEBOUNCE_GRACE_SECONDS = 15


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
    permission_scope = PERMISSION_CREWMATE
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
                        "quick=45s targeted lookup, standard=90s balanced, "
                        "deep=150s multi-subsystem sweep"
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
        budget = EXPLORE_BUDGETS.get(thoroughness, EXPLORE_BUDGETS["standard"])

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
        started = time.monotonic()
        try:
            async with asyncio.timeout(budget["timeout_s"] + _EXPLORE_DEBOUNCE_GRACE_SECONDS):
                async with _spawn_semaphore:
                    async for _event in orchestrator.investigate(
                        mission_objective,
                        definition,
                        parent_session_id=f"explore:{workspace_root}",
                        timeout_seconds=budget["timeout_s"],
                        max_context_tokens=budget["context_tokens"],
                    ):
                        # Child lifecycle events never enter the parent
                        # context (D5); terminal state comes from last_result.
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
                metadata=self._metadata(
                    thoroughness,
                    status="failed",
                    crewmate_name=definition.name,
                    crewmate_role=definition.role,
                ),
            )
        elapsed_ms = int((time.monotonic() - started) * 1000)

        result = orchestrator.last_result
        if result is None:
            return ToolResult(
                success=False,
                error="Explore mission produced no result.",
                metadata=self._metadata(thoroughness, crewmate_name=definition.name),
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
                timeout=optional_float(ENRICH_TIMEOUT_ENV, DEFAULT_ENRICH_TIMEOUT_SECONDS),
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
