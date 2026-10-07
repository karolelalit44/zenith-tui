"""Apogee Crewmate runner: bounded read-only investigation.

Owns the mission mechanics for the first specialist agent:

- ``CrewmateReadOnlyGuard`` middleware — structural backstop that blocks every
  non-read tool while ``ctx.mode == CREWMATE_MODE`` (``file_write``/``file_edit``
  are not mode-gated, so the schema-surface filter alone is not enough);
- ``build_crewmate_prompt`` — objective + read-only mandate + AgentResult JSON
  output contract + evidence rules;
- ``run_crewmate`` — fresh ``ContextManager`` + ``RecoverableAgentLoop`` in
  ``CREWMATE_MODE``; yields forwardable child events while intercepting
  SUCCESS/ERROR into a ``CrewmateRun`` outcome;
- ``assemble_result`` — parses the fenced AgentResult JSON block and applies
  the evidence rule (a verified claim must cite path+snippet).
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from server.config.constants import (
    CREWMATE_MODE,
    CREWMATE_OBSERVATION_CHARS,
    CREWMATE_TOOL_CALL_LIMIT,
    DISCOVER_CAPABILITIES_TOOL,
    GET_TOOL_DEFINITION_TOOL,
    READ_ONLY_TOOLS,
)
from server.config.settings import AGENT_MODES, AppSettings
from server.domain.events import Event, EventKind
from server.providers.base import BaseProvider
from server.toolkit.base import ToolMiddleware, ToolResult
from server.toolkit.registry import ToolRegistry

from .agent_definition import AgentDefinition
from .agent_result import AgentMetrics, AgentResult
from .task_envelope import AgentTask

logger = logging.getLogger(__name__)

# Raw child events the parent transcript may see. SUCCESS/ERROR are
# intercepted by the runner so the TUI never finalizes mid-crewmate. THINKING is
# deliberately NOT forwarded: per-turn reasoning re-rendered in the parent
# produced walls of near-identical blocks (2026-08-26 incident); the captain
# timeline already summarizes activity.
FORWARDABLE_KINDS = frozenset(
    {
        EventKind.MESSAGE,
        EventKind.TOOL_CALL,
        EventKind.TOOL_RESULT,
        EventKind.WARNING,
    }
)

MESSAGE_FORWARD_MAX_CHARS = 2_000
ACTIVITY_MAX_CHARS = 200

# Read tools plus the dynamic-escalation discovery pair: a crewmate may ask for
# another schema, but never gain a mutation tool through it.

_CREWMATE_ALLOWED_TOOLS = (
    frozenset(READ_ONLY_TOOLS)
    | {
        DISCOVER_CAPABILITIES_TOOL,
        GET_TOOL_DEFINITION_TOOL,
    }
)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_NO_REPORT_SENTINELS = frozenset({"[empty assistant turn]"})


class CrewmateReadOnlyGuard(ToolMiddleware):
    """Reject any tool outside the crewmate allow-list while in CREWMATE_MODE."""

    def __init__(self) -> None:
        self.blocked_calls = 0

    async def before_execute(self, name: str, params: dict, ctx) -> bool | ToolResult:
        if ctx.mode != CREWMATE_MODE:
            return True
        if name in _CREWMATE_ALLOWED_TOOLS:
            return True
        self.blocked_calls += 1
        return ToolResult(
            success=False,
            error=(
                f"Tool '{name}' is blocked for {ctx.mode} agents: "
                "investigation is strictly read-only."
            ),
        )


def register_crewmate_guard(registry: ToolRegistry) -> CrewmateReadOnlyGuard:
    """Register the guard on the shared registry once (dedupe by type)."""
    for mw in getattr(registry, "_middleware", []):
        if isinstance(mw, CrewmateReadOnlyGuard):
            return mw
    guard = CrewmateReadOnlyGuard()
    registry.register_middleware(guard)
    return guard


@dataclass
class CrewmateRun:
    """Mutable outcome accumulator filled while the child loop streams."""

    response_text: str = ""
    last_error: str | None = None
    token_info: dict = field(default_factory=dict)
    iterations: int = 0
    tool_calls: int = 0
    elapsed_ms: int = 0
    # Set when the mission was cut off at the tool-call ceiling before the
    # crewmate produced a report. Distinguishes "the model chose to stop" from
    # "the harness stopped it", which the parent needs in order to read the
    # outcome truthfully.
    budget_exhausted: bool = False
    # Raw tool observations gathered before the cut, kept so a truncated mission
    # can still hand the parent something real rather than a fabricated finding.
    observations: list[str] = field(default_factory=list)


def _truncate_event(event: Event, key: str, limit: int) -> Event:
    text = event.data.get(key)
    if isinstance(text, str) and len(text) > limit:
        event.data[key] = text[:limit] + "…"
    return event


def build_crewmate_prompt(task: AgentTask, mission_brief: str | None = None) -> str:
    parts = [
        "You are on a delegated investigation mission.",
        f"Agent id: {task.agent_id}. Task id: {task.task_id}.",
        "",
        "OBJECTIVE:",
        task.objective.strip(),
    ]
    if mission_brief:
        
        parts += ["", "MISSION BRIEF (precomputed orientation; advisory):", mission_brief.strip()]
    parts += [
        "",
        "READ-ONLY MANDATE:",
        "- Investigate using discovery/read tools only (file_read, glob, grep, list_dir).",
        "- You MUST NOT create, modify or delete anything; mutation attempts are rejected.",
        "- Stay focused on the objective; keep tool calls small and targeted.",
    ]
    if task.scoped_instructions:
        parts += ["", "SCOPED INSTRUCTIONS:", task.scoped_instructions.strip()]
    if task.context_digest:
        parts += [
            "",
            "CONTEXT DIGEST (what the Captain already knows):",
            task.context_digest.strip(),
        ]
    parts += [
        "",
        "OUTPUT CONTRACT (mandatory):",
        "End your reply with ONE fenced ```json block containing exactly this shape:",
        "```json",
        json.dumps(
            {
                "task_id": task.task_id,
                "agent_id": task.agent_id,
                "status": "completed",
                "summary": "<3-6 sentence answer to the objective>",
                "findings": [
                    {
                        "claim": "...",
                        "confidence": "verified|proposed|unverified",
                        "evidence_refs": ["0"],
                    }
                ],
                "evidence": [
                    {
                        "type": "file_read",
                        "path": "relative/path.py",
                        "snippet": "<short verbatim code quote>",
                    }
                ],
                "affected_files": ["<paths the objective would touch>"],
                "proposed_changes": ["<what would need to change>"],
                "unverified": ["<claims you could not confirm>"],
                "blocked": ["<what you could not inspect and why>"],
            },
            indent=2,
        ),
        "```",
        "EVIDENCE RULES:",
        '- confidence="verified" REQUIRES at least one evidence_refs entry '
        + "pointing at evidence with BOTH a path and a snippet.",
        "- Anything you did not personally verify with a tool call must be "
        + 'confidence="proposed" or listed under unverified.',
        "- Do not fabricate paths or snippets.",
        "",
        "STOP CONDITIONS:",
        (
            "- Stop as soon as the objective is answerable with cited evidence; "
            'do not keep reading "for completeness".'
        ),
        "- If you catch yourself opening the same file twice, stop and write the report.",
        "- Prefer finishing with honest unverified[] entries over exceeding your budget.",
        "",
        "RETREAT CLAUSE:",
        (
            "- Reporting absence is a SUCCESS. If ~5 distinct searches (vary "
            "tool, terms, and scope) yield no trace of the target, STOP and "
            'return status=completed with the target listed under "blocked" '
            'or "unverified" - e.g. "no X found in <scope searched>". Do not '
            "keep hunting for something that is not there."
        ),
    ]
    return "\n".join(parts)



CREWMATE_SALVAGE_INSTRUCTION = (
    "You have run out of steps. Produce your FINAL REPORT now as ONE fenced "
    "```json block matching the OUTPUT CONTRACT above, using only evidence "
    "already gathered in this conversation. No tools are available. List "
    'unfinished threads under "unverified" and inaccessible areas under '
    '"blocked". Reporting that the target does not exist is a valid '
    "completed report - say so explicitly with the scope you searched. Do "
    "not fabricate paths or snippets."
)


def build_mission_brief(workspace_root: str) -> str | None:
    """Precomputed orientation block: workspace shape + hub symbols (WP6).

    Best-effort by design — any failure returns ``None`` and the crewmate simply
    explores without a brief. Hard-capped so it can never dominate the child
    prompt.
    """
    try:
        from server.config.constants import EXPLORE_BRIEF_MAX_CHARS
        from server.workspace.index import get_workspace_stats

        stats = get_workspace_stats(workspace_root)
        lines = [
            f"Workspace: ~{stats.total_files} files ({stats.describe_top_level(8)}).",
        ]
        brief = "\n".join(lines).strip()
        return brief[:EXPLORE_BRIEF_MAX_CHARS] if brief else None
    except Exception as e:
        logger.debug("Mission brief skipped: %s", e)
        return None


async def run_crewmate(
    *,
    config: AppSettings,
    provider: BaseProvider,
    tool_registry: ToolRegistry,
    compaction_service=None,
    task: AgentTask,
    definition: AgentDefinition,
    run: CrewmateRun | None = None,
) -> AsyncIterator[Event]:
    """Execute the mission in a fresh context; yield forwardable child events.

    SUCCESS is intercepted into ``run.token_info``/``iterations`` and ERROR
    into ``run.last_error`` — neither is yielded; terminal semantics belong
    to the orchestrator.
    """
    from server.agents.context import ContextManager
    from server.agents.recovery import RecoverableAgentLoop

    run = run if run is not None else CrewmateRun()
    budget = min(config.max_context_tokens, max(task.max_context_tokens, 1))
    crewmate_config = config.model_copy(update={"max_context_tokens": budget})
    context_manager = ContextManager(crewmate_config)
    agent = RecoverableAgentLoop(
        crewmate_config,
        provider,
        context_manager,
        tool_registry,
        compaction_service,
    )
    
    agent._salvage_instruction = CREWMATE_SALVAGE_INSTRUCTION
    mode_config = AGENT_MODES.get(CREWMATE_MODE)
    model_override = definition.model_override or (
        mode_config.model_override if mode_config else None
    )
    started = time.monotonic()
    mission_brief = build_mission_brief(str(crewmate_config.workspace_root))

    def _budget_note() -> str:
        return (
            f"Crewmate hit the {CREWMATE_TOOL_CALL_LIMIT}-tool-call ceiling for a delegated "
            "mission and was stopped before producing an evidence report."
        )

    try:
        async for event in agent.process_prompt(
            prompt=build_crewmate_prompt(task, mission_brief),
            session_id=task.child_session_id or task.task_id,
            history=[],
            mode=CREWMATE_MODE,
            model_override=model_override,
        ):
            kind = event.kind
            if kind == EventKind.SUCCESS:
                run.iterations = int(event.data.get("iterations") or 0)
                token_info = event.data.get("tokenInfo")
                if not isinstance(token_info, dict):
                    token_info = {
                        k: event.data[k]
                        for k in ("used", "total", "remaining", "percent")
                        if k in event.data
                    }
                run.token_info = token_info
                continue
            if kind == EventKind.ERROR:
                run.last_error = str(event.data.get("message") or "unknown crewmate error")
                continue
            # Enforce the documented forwarding contract: only FORWARDABLE_KINDS
            # cross the parent boundary. THINKING in particular is deliberately
            # dropped (2026-08-26 incident) — per-turn reasoning re-rendered in
            # the parent produced walls of near-identical blocks.
            if kind not in FORWARDABLE_KINDS:
                continue
            if kind == EventKind.MESSAGE:
                text = event.data.get("text") or ""
                if not event.data.get("partial"):
                    run.response_text += text
                yield _truncate_event(event, "text", MESSAGE_FORWARD_MAX_CHARS)
                continue
            if kind == EventKind.TOOL_CALL:
                run.tool_calls += 1
                yield event
                continue
            if kind == EventKind.TOOL_RESULT:
                output = str(event.data.get("output") or event.data.get("error") or "").strip()
                if output:
                    tool = str(event.data.get("tool") or "tool")
                    success = event.data.get("success")
                    run.observations.append(
                        f"{tool} {'ok' if success else 'failed'}: {output[:CREWMATE_OBSERVATION_CHARS]}"
                    )
                yield event
                if run.tool_calls >= CREWMATE_TOOL_CALL_LIMIT and not run.response_text.strip():
                    # Stop the child loop and let assemble_result report the
                    # truncation. Synthesising a completed report here would
                    # hand the parent a finding the crewmate never made.
                    run.budget_exhausted = True
                    run.last_error = _budget_note()
                    return
                continue
            if kind == EventKind.WARNING:
                yield event
                continue
    finally:
        run.elapsed_ms = int((time.monotonic() - started) * 1000)


def assemble_result(
    task: AgentTask,
    definition: AgentDefinition,
    run: CrewmateRun,
    *,
    status: str = "completed",
    error: str | None = None,
) -> AgentResult:
    """Build an ``AgentResult`` from the crewmate's final fenced JSON block.

    Falls back to an unverified prose result when no parseable block exists.
    Applies the evidence rule before returning.
    """
    metrics = AgentMetrics(
        tokens_used=int((run.token_info or {}).get("used") or 0),
        iterations=run.iterations,
        elapsed_ms=run.elapsed_ms,
        tool_calls=run.tool_calls,
    )
    response_text = run.response_text.strip()
    has_report_text = bool(response_text) and response_text not in _NO_REPORT_SENTINELS
    parsed: dict | None = None
    for match in _JSON_FENCE_RE.finditer(response_text):
        candidate = match.group(1).strip()
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            parsed = data
    if run.budget_exhausted:
        # Truncated mission. The observations below are real — they came from
        # tool calls this run actually made — but nothing here was verified, and
        # the crewmate never reached a conclusion, so the result is a failure
        # carrying unverified evidence rather than a completed report.
        note = error or run.last_error or "Crewmate was stopped before reporting."
        result = AgentResult(
            task_id=task.task_id,
            agent_id=definition.id,
            status="failed",
            summary=note,
            blocked=[note],
            unverified=list(run.observations),
            metrics=metrics,
            error=note,
        )
        result.apply_evidence_rule()
        return result
    if parsed is None:
        if not has_report_text:
            missing_report = "Crewmate ended without a final evidence report."
            if run.tool_calls > 0:
                missing_report += f" It made {run.tool_calls} read-only tool call(s) before stopping."
            result = AgentResult(
                task_id=task.task_id,
                agent_id=definition.id,
                status="failed" if status == "completed" else status,
                summary=missing_report,
                blocked=[missing_report],
                metrics=metrics,
                error=error or missing_report,
            )
            result.apply_evidence_rule()
            return result
        result = AgentResult(
            task_id=task.task_id,
            agent_id=definition.id,
            status=status,
            summary=response_text,
            unverified=[response_text],
            metrics=metrics,
            error=error,
        )
        result.apply_evidence_rule()
        return result
    payload = dict(parsed)
    payload.pop("metrics", None)
    result = AgentResult.model_validate(
        {
            **payload,
            "task_id": task.task_id,
            "agent_id": definition.id,
            "status": status,
            "metrics": metrics,
            **({"error": error} if error else {}),
        }
    )
    result.apply_evidence_rule()
    return result
