"""Codebase Scout runner: bounded read-only investigation.

Owns the mission mechanics for the first specialist agent:

- ``ScoutReadOnlyGuard`` middleware — structural backstop that blocks every
  non-read tool while ``ctx.mode == SCOUT_MODE`` (``file_write``/``file_edit``
  are not mode-gated, so the schema-surface filter alone is not enough);
- ``build_scout_prompt`` — objective + read-only mandate + AgentResult JSON
  output contract + evidence rules;
- ``run_scout`` — fresh ``ContextManager`` + ``RecoverableAgentLoop`` in
  ``SCOUT_MODE``; yields forwardable child events while intercepting
  SUCCESS/ERROR into a ``ScoutRun`` outcome;
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
    DISCOVER_CAPABILITIES_TOOL,
    GET_TOOL_DEFINITION_TOOL,
    READ_ONLY_TOOLS,
    SCOUT_MODE,
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
# intercepted by the runner so the TUI never finalizes mid-scout.
FORWARDABLE_KINDS = frozenset(
    {
        EventKind.MESSAGE,
        EventKind.TOOL_CALL,
        EventKind.TOOL_RESULT,
        EventKind.THINKING,
        EventKind.WARNING,
    }
)

MESSAGE_FORWARD_MAX_CHARS = 2_000
THINKING_FORWARD_MAX_CHARS = 500
ACTIVITY_MAX_CHARS = 200

# Read tools plus the dynamic-escalation discovery pair: a scout may ask for
# another schema, but never gain a mutation tool through it.
_SCOUT_ALLOWED_TOOLS = frozenset(READ_ONLY_TOOLS) | {
    DISCOVER_CAPABILITIES_TOOL,
    GET_TOOL_DEFINITION_TOOL,
}

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class ScoutReadOnlyGuard(ToolMiddleware):
    """Reject any tool outside the scout allow-list while in SCOUT_MODE."""

    def __init__(self) -> None:
        self.blocked_calls = 0

    async def before_execute(self, name: str, params: dict, ctx) -> bool | ToolResult:
        if ctx.mode != SCOUT_MODE:
            return True
        if name in _SCOUT_ALLOWED_TOOLS:
            return True
        self.blocked_calls += 1
        return ToolResult(
            success=False,
            error=(
                f"Tool '{name}' is blocked for {ctx.mode} agents: "
                "investigation is strictly read-only."
            ),
        )


def register_scout_guard(registry: ToolRegistry) -> ScoutReadOnlyGuard:
    """Register the guard on the shared registry once (dedupe by type)."""
    for mw in getattr(registry, "_middleware", []):
        if isinstance(mw, ScoutReadOnlyGuard):
            return mw
    guard = ScoutReadOnlyGuard()
    registry.register_middleware(guard)
    return guard


@dataclass
class ScoutRun:
    """Mutable outcome accumulator filled while the child loop streams."""

    response_text: str = ""
    last_error: str | None = None
    token_info: dict = field(default_factory=dict)
    iterations: int = 0
    tool_calls: int = 0
    elapsed_ms: int = 0


def _truncate_event(event: Event, key: str, limit: int) -> Event:
    text = event.data.get(key)
    if isinstance(text, str) and len(text) > limit:
        event.data[key] = text[:limit] + "…"
    return event


def build_scout_prompt(task: AgentTask) -> str:
    parts = [
        "You are on a delegated investigation mission.",
        f"Agent id: {task.agent_id}. Task id: {task.task_id}.",
        "",
        "OBJECTIVE:",
        task.objective.strip(),
        "",
        "READ-ONLY MANDATE:",
        "- Investigate using discovery/read tools only (file_read, glob, grep, list_dir).",
        "- You MUST NOT create, modify or delete anything; mutation attempts are rejected.",
        "- Stay focused on the objective; keep tool calls small and targeted.",
    ]
    if task.scoped_instructions:
        parts += ["", "SCOPED INSTRUCTIONS:", task.scoped_instructions.strip()]
    if task.context_digest:
        parts += ["", "CONTEXT DIGEST (what the Captain already knows):", task.context_digest.strip()]
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
        '- Anything you did not personally verify with a tool call must be '
        + 'confidence="proposed" or listed under unverified.',
        "- Do not fabricate paths or snippets.",
    ]
    return "\n".join(parts)


async def run_scout(
    *,
    config: AppSettings,
    provider: BaseProvider,
    tool_registry: ToolRegistry,
    compaction_service=None,
    task: AgentTask,
    definition: AgentDefinition,
    run: ScoutRun | None = None,
) -> AsyncIterator[Event]:
    """Execute the mission in a fresh context; yield forwardable child events.

    SUCCESS is intercepted into ``run.token_info``/``iterations`` and ERROR
    into ``run.last_error`` — neither is yielded; terminal semantics belong
    to the orchestrator.
    """
    from server.agents.context import ContextManager
    from server.agents.recovery import RecoverableAgentLoop

    run = run if run is not None else ScoutRun()
    budget = min(config.max_context_tokens, max(task.max_context_tokens, 1))
    scout_config = config.model_copy(update={"max_context_tokens": budget})
    context_manager = ContextManager(scout_config)
    agent = RecoverableAgentLoop(
        scout_config,
        provider,
        context_manager,
        tool_registry,
        compaction_service,
    )
    mode_config = AGENT_MODES.get(SCOUT_MODE)
    model_override = definition.model_override or (
        mode_config.model_override if mode_config else None
    )
    started = time.monotonic()
    try:
        async for event in agent.process_prompt(
            prompt=build_scout_prompt(task),
            session_id=task.child_session_id or task.task_id,
            history=[],
            mode=SCOUT_MODE,
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
                run.last_error = str(event.data.get("message") or "unknown scout error")
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
                yield event
                continue
            if kind == EventKind.THINKING:
                yield _truncate_event(event, "text", THINKING_FORWARD_MAX_CHARS)
                continue
            if kind == EventKind.WARNING:
                yield event
                continue
    finally:
        run.elapsed_ms = int((time.monotonic() - started) * 1000)


def assemble_result(
    task: AgentTask,
    definition: AgentDefinition,
    run: ScoutRun,
    *,
    status: str = "completed",
    error: str | None = None,
) -> AgentResult:
    """Build an ``AgentResult`` from the scout's final fenced JSON block.

    Falls back to an unverified prose result when no parseable block exists.
    Applies the evidence rule before returning.
    """
    metrics = AgentMetrics(
        tokens_used=int((run.token_info or {}).get("used") or 0),
        iterations=run.iterations,
        elapsed_ms=run.elapsed_ms,
        tool_calls=run.tool_calls,
    )
    parsed: dict | None = None
    for match in _JSON_FENCE_RE.finditer(run.response_text):
        candidate = match.group(1).strip()
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            parsed = data
    if parsed is None:
        result = AgentResult(
            task_id=task.task_id,
            agent_id=definition.id,
            status=status,
            summary=run.response_text.strip(),
            unverified=[run.response_text.strip()] if run.response_text.strip() else [],
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
