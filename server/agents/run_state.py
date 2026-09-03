"""Structured session run state (QA-4).

A ``SessionRunState`` is the authoritative, evidence-derived record of what a
session is doing and has done. It is built from *executed* tool events and turn
manifests — never from model prose. The spec's statuses are:
``investigating / planning / executing / verifying / finalizing / blocked /
failed / completed``.

The state is persisted into ``session.metadata["run_state"]`` (an additive key,
so older sessions without it initialize safely). Frontend panels (activity feed,
todo board, final summary card) render from this contract rather than inferring
state from prose.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from server.domain.events import EventKind

# Run statuses per the design spec (Phase 5). ``idle`` is the safe default for a
# session that has not executed anything yet.
RUN_STATUSES = (
    "idle",
    "investigating",
    "planning",
    "executing",
    "verifying",
    "finalizing",
    "blocked",
    "failed",
    "completed",
)

# Event kinds that count as observable activity for the tool history.
_TOOL_ACTIVITY_KINDS = {EventKind.TOOL_CALL, EventKind.TOOL_RESULT}
_FINAL_KINDS = {EventKind.SUCCESS, EventKind.ERROR, EventKind.WARNING}


@dataclass
class RunStep:
    """One executed (or attempted) tool step in this session's run."""

    kind: str  # "tool_call" | "tool_result" | "message" | "thinking" | ...
    tool: str | None = None
    status: str | None = None  # "started" | "success" | "error"
    summary: str | None = None  # compact digest, never full tool output
    seq: int = 0
    ts: float = 0.0


@dataclass
class SessionRunState:
    objective: str = ""
    mode: str = "build"
    status: str = "idle"
    todo: list[dict] = field(default_factory=list)
    plan: str = ""
    findings: list[str] = field(default_factory=list)
    tool_history: list[dict] = field(default_factory=list)
    progress: list[dict] = field(default_factory=list)
    manifest: dict[str, Any] | None = None
    final: dict[str, Any] | None = None
    started_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Cap tool history so the persisted record stays bounded.
        data["tool_history"] = data["tool_history"][-_MAX_TOOL_HISTORY:]
        data["progress"] = data["progress"][-_MAX_PROGRESS:]
        return data


# Bounded history/progress: a long run must not balloon session metadata.
_MAX_TOOL_HISTORY = 40
_MAX_PROGRESS = 24
_MAX_FINDINGS = 50


def _append_finding(state: SessionRunState, note: str) -> None:
    """Record an evidence-derived finding, deduplicated and bounded."""
    note = note.strip()
    if not note:
        return
    if note in state.findings:
        return
    state.findings.append(note)
    if len(state.findings) > _MAX_FINDINGS:
        state.findings = state.findings[-_MAX_FINDINGS:]


def new_run_state(objective: str = "", mode: str = "build", ts: float = 0.0) -> SessionRunState:
    return SessionRunState(
        objective=(objective or "").strip(),
        mode=mode,
        status="idle",
        started_at=ts,
        updated_at=ts,
    )


def from_dict(data: dict[str, Any] | None) -> SessionRunState:
    """Hydrate from a persisted dict; safe default when absent/malformed."""
    if not data or not isinstance(data, dict):
        return SessionRunState()
    return SessionRunState(
        objective=str(data.get("objective") or ""),
        mode=str(data.get("mode") or "build"),
        status=str(data.get("status") or "idle"),
        todo=list(data.get("todo") or []),
        plan=str(data.get("plan") or ""),
        findings=list(data.get("findings") or [])[-_MAX_FINDINGS:],
        tool_history=list(data.get("tool_history") or [])[-_MAX_TOOL_HISTORY:],
        progress=list(data.get("progress") or [])[-_MAX_PROGRESS:],
        manifest=data.get("manifest"),
        final=data.get("final"),
        started_at=float(data.get("started_at") or 0),
        updated_at=float(data.get("updated_at") or 0),
    )


def merge_run_state(previous: SessionRunState | None, ts: float = 0.0) -> SessionRunState:
    """Start a fresh run building on a previous session's persisted state.

    Todo and plan carry over (a resumed session continues its plan); activity
    history and findings are reset to the new turn. Findings are per-run
    evidence (AGENT_RELIABILITY_PLAN P2.3): carrying them forward made a stale
    failure from an earlier attempt surface on a later successful run's
    summary card.
    """
    base = previous or SessionRunState()
    return SessionRunState(
        objective=base.objective,
        mode=base.mode,
        status="idle",
        todo=list(base.todo),
        plan=base.plan,
        findings=[],
        tool_history=[],
        progress=[],
        manifest=None,
        final=None,
        started_at=ts or base.started_at,
        updated_at=ts or base.updated_at,
    )


def _activity_label(tool: str, seq: int, detail: str = "") -> str:
    """Map an executed tool to a short, human-facing progress label.

    Labels are derived from the tool that actually ran - never fabricated
    narration. Unknown tools fall back to a stable ``Running tool <name>``
    label so the activity feed never invents steps. When ``detail`` is
    provided (command/path/pattern snippet) it is appended so consecutive
    same-tool steps are visually distinct.
    """
    labels = {
        "file_read": "Reading files",
        "file_write": "Writing files",
        "file_edit": "Editing files",
        "file_delete": "Deleting files",
        "glob_search": "Searching for files",
        "grep_search": "Searching code",
        "bash": "Running commands",
        "terminal": "Running commands",
        "job_start": "Launching background job",
        "job_output": "Checking background job",
        "todo": "Managing todos",
        "plan_write": "Writing plan",
        "plan_read": "Reading plan",
    }
    label = labels.get(tool, f"Running {tool}" if tool else "Working")
    if detail:
        label = f"{label}: {detail}"
    return label


def update_from_event(
    state: SessionRunState, kind: EventKind, data: dict[str, Any], ts: float
) -> None:
    """Fold one event into the run state (evidence-only, no prose inference).

    Tool activity advances the ``tool_history``/``progress`` and the status
    machine; a turn manifest records the authoritative created/modified record;
    a SUCCESS/ERROR/WARNING closes the run with a ``final`` outcome.
    """
    state.updated_at = ts
    kind_str = kind.value

    if kind in _TOOL_ACTIVITY_KINDS:
        tool = str(data.get("tool") or "")
        seq = int(data.get("seq") or len(state.tool_history) + 1)
        if kind == EventKind.TOOL_CALL:
            step = RunStep(kind="tool_call", tool=tool, status="started", seq=seq, ts=ts)
            state.tool_history.append(_step_to_dict(step))
            state.progress.append({"label": _activity_label(tool, seq), "seq": seq, "ts": ts})
            if state.status in ("idle", "planning"):
                state.status = "executing"
        elif kind == EventKind.TOOL_RESULT:
            success = bool(data.get("success"))
            status = "success" if success else "error"
            step = RunStep(
                kind="tool_result",
                tool=tool,
                status=status,
                summary=_result_summary(data),
                seq=seq,
                ts=ts,
            )
            state.tool_history.append(_step_to_dict(step))
            if success and state.status == "executing":
                state.status = "verifying"
            elif not success and state.status != "blocked":
                state.status = "blocked"

    elif kind == EventKind.TURN_MANIFEST:
        m = data.get("manifest")
        if isinstance(m, dict):
            state.manifest = m
            created = m.get("created") or []
            modified = m.get("modified") or []
            if created or modified:
                state.status = "finalizing" if m.get("completed") else "verifying"
            # Verification checks with output are evidence the run discovered;
            # record them as compact findings (QA-9.2 "discovered").
            for check in m.get("checks") or []:
                if not isinstance(check, dict):
                    continue
                if (check.get("output_len") or 0) > 0 and check.get("tool"):
                    _append_finding(
                        state,
                        f"Verified via {check['tool']} (evidence: {check['output_len']} chars)",
                    )

    elif kind in _FINAL_KINDS:
        state.final = {
            "kind": kind_str,
            "message": str(data.get("message") or "").strip()[:400],
            "code": data.get("code"),
            "ts": ts,
        }
        if kind == EventKind.SUCCESS:
            state.status = "completed"
        elif kind == EventKind.ERROR:
            state.status = "failed"
            if state.final["message"]:
                _append_finding(state, f"Run failed: {state.final['message']}")
        # WARNING keeps the current status (does not close the run).


def _step_to_dict(step: RunStep) -> dict[str, Any]:
    return {
        "kind": step.kind,
        "tool": step.tool,
        "status": step.status,
        "summary": step.summary,
        "seq": step.seq,
        "ts": step.ts,
    }


def _result_summary(data: dict[str, Any]) -> str:
    """Compact digest of a tool result — full output never enters run state."""
    out = str(data.get("output") or "")
    err = str(data.get("error") or "")
    if not out and not err:
        return ""
    if err:
        return f"error: {err[:140]}"
    return out[:160].strip()
