"""Dry-run scenario matrix.

Scripted stub providers are replayed through the REAL ``AgentLoop`` (no network,
no real LLM) and every emitted event is checked against the behavior the code is
supposed to have. Each scenario carries explicit expected-event checks plus the
cross-cutting invariants:

* I1 - tool pairing: every ``tool_result`` is FIFO-paired to a preceding
  ``tool_call`` of the same tool (the TUI ghost-card regression).
* I2 - no duplicate final answer text (``partial=False`` messages).
* I3 - every event carries a session id.

Run with:  python -m pytest server/tests/test_dryrun_scenarios.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from server.agents.compaction import compact_tool_output, head_tail_trim
from server.agents.loop import (
    AgentLoop,
    _all_calls_repeat,
    _build_manifest,
    _call_signature,
    _find_compaction_cut,
    _find_compaction_cut_budgeted,
    _group_start,
    _has_verification_evidence,
    _most_common_count,
    _params_label,
)
from server.agents.session_workspace import reset_session
from server.agents.validation import reflection_error_limit, schemas_to_openai_tools
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.domain.domain import FinishReason
from server.domain.errors import RateLimitError
from server.domain.events import Event, EventKind
from server.providers.base import BaseProvider
from server.providers.parser import UnifiedResponseFormatter
from server.toolkit import create_default_registry
from server.toolkit.command_safety import assess_command, is_command_banned
from server.toolkit.executor import (
    _dynamic_max_output,
    validate_tool_calls,
    validate_tool_rejection,
)

# ---------------------------------------------------------------------------
# Scripted provider
# ---------------------------------------------------------------------------


_PY = ("python" if " " in sys.executable else sys.executable.replace("\\", "/"))


class _DryRunProvider(BaseProvider):
    """Plays a script of responses through the real streaming path.

    Each entry is either:
    * a ``str`` (the whole assistant response; streamed char by char), or
    * a ``dict``: ``{"text": ..., "finish_reason": ..., "raise": exc}``, or
    * a callable ``(messages) -> str | dict`` for stateful scripts.

    The script index never runs past the last entry (it repeats forever), which
    lets a two-step script also model a stalled model.
    """

    def __init__(self, scripts, name="dryrun", model="test-model"):
        super().__init__(name, model)
        self.scripts = list(scripts)
        self.call_count = 0
        self.offered_tools: list[str] | None = None
        self._last_finish_reason = FinishReason.STOP

    async def complete(self, messages, tools=None):
        idx = min(self.call_count, len(self.scripts) - 1)
        self.call_count += 1
        entry = self.scripts[idx]
        if callable(entry):
            entry = entry(messages)
        if isinstance(entry, dict) and "raise" in entry:
            raise entry["raise"]
        if isinstance(entry, dict):
            self._last_finish_reason = entry.get("finish_reason", FinishReason.STOP)
            return entry.get("text", "")
        self._last_finish_reason = FinishReason.STOP
        return entry

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        if self.offered_tools is None:
            self.offered_tools = [
                t.get("function", {}).get("name") for t in (tools or []) if t.get("function")
            ]
        response = await self.complete(messages, tools)
        for char in response:
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["test-model"]


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------


def _warnings(events: list[Event]) -> list[str]:
    return [e.data.get("message", "") for e in events if e.kind == EventKind.WARNING]


def _errors(events: list[Event]) -> list[Event]:
    return [e for e in events if e.kind == EventKind.ERROR]


def _full_messages(events: list[Event]) -> list[str]:
    return [
        e.data.get("text", "")
        for e in events
        if e.kind == EventKind.MESSAGE and not e.data.get("partial")
    ]


def _manifests(events: list[Event]) -> list[dict]:
    return [e.data for e in events if e.kind == EventKind.TURN_MANIFEST]


def _has_warning(events: list[Event], needle: str) -> bool:
    return any(needle in m for m in _warnings(events))


def _check_global_invariants(events: list[Event]) -> None:
    pending: dict[str, list] = {}
    for ev in events:
        if ev.kind == EventKind.TOOL_CALL:
            pending.setdefault(ev.data["tool"], []).append(ev)
        elif ev.kind == EventKind.TOOL_RESULT:
            tool = ev.data["tool"]
            assert pending.get(tool), f"orphan tool_result for '{tool}' (no matching tool_call)"
            pending[tool].pop(0)
    for tool, rest in pending.items():
        assert not rest, f"{len(rest)} tool_call(s) for '{tool}' never got a result"
    seen: set[str] = set()
    for text in _full_messages(events):
        assert text not in seen, f"duplicate final answer text emitted twice: {text!r}"
        seen.add(text)
    assert all(ev.session_id for ev in events), "some events are missing a session_id"


def _require(events: list[Event], desc: str, cond: bool) -> None:
    assert cond, desc


def _config(temp_dir: Path, **overrides) -> AppSettings:
    base = {
        "providers": {"test": ProviderConfig(model="test-model", is_active=True)},
        "active_provider": "test",
        "db_path": str(temp_dir / "test.db"),
        "workspace_root": str(temp_dir),
    }
    base.update(overrides)
    return AppSettings(**base)


async def _run(
    provider: BaseProvider,
    config: AppSettings,
    *,
    mode: str = "build",
    prompt: str = "Do the work",
    cancel_after: int | None = None,
    session_id: str = "s1",
    reset_registry: bool = True,
) -> list[Event]:
    agent = AgentLoop(config, provider, tool_registry=create_default_registry())
    events: list[Event] = []
    # The durable session registry is keyed by session_id; every scenario here
    # reuses "s1", so clear any state an earlier scenario may have recorded.
    if reset_registry:
        reset_session(session_id)

    async def collect() -> None:
        async for ev in agent.process_prompt(prompt, session_id, [], mode):
            events.append(ev)
            if cancel_after is not None and len(events) == cancel_after:
                agent.cancel()

    await collect()
    return events


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

SCENARIOS: list[dict] = [
    {
        "name": "S01_echo_text_only",
        "desc": "Text-only turn: one full message, clean manifest, terminal success.",
        "prompt": "Say hello",
        "scripts": ["Hello there!"],
        "checks": [
            ("exactly one full message", lambda e, p, c: _require(e, "message count", len(_full_messages(e)) == 1)),
            ("message text matches", lambda e, p, c: _require(e, "text", _full_messages(e)[0] == "Hello there!")),
            ("no tool events", lambda e, p, c: _require(e, "no tools", not any(x.kind in (EventKind.TOOL_CALL, EventKind.TOOL_RESULT) for x in e))),
            ("manifest completed", lambda e, p, c: _require(e, "manifest", _manifests(e) and _manifests(e)[-1].get("completed") is True)),
            ("manifest not stalled", lambda e, p, c: _require(e, "stalled", _manifests(e)[-1].get("stalled") is False)),
            ("no created files", lambda e, p, c: _require(e, "created", _manifests(e)[-1].get("created") == [])),
            ("terminal success only", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
        ],
    },
    {
        "name": "S02_single_file_write",
        "desc": "file_write executes once; manifest lists it; success.",
        "scripts": [
            '```tool\n{"tool": "file_write", "params": {"path": "out.txt", "content": "hello"}}\n```',
            "Done.",
        ],
        "checks": [
            ("file created with content", lambda e, p, c: _require(e, "content", (Path(c.workspace_root) / "out.txt").read_text(encoding="utf-8") == "hello")),
            ("one tool_call for file_write", lambda e, p, c: _require(e, "calls", sum(1 for x in e if x.kind == EventKind.TOOL_CALL and x.data.get("tool") == "file_write") == 1)),
            ("one successful tool_result", lambda e, p, c: _require(e, "results", sum(1 for x in e if x.kind == EventKind.TOOL_RESULT and x.data.get("tool") == "file_write" and x.data.get("success")) == 1)),
            ("manifest created lists file", lambda e, p, c: _require(e, "created", "out.txt" in _manifests(e)[-1].get("created", []))),
            ("manifest files exists", lambda e, p, c: _require(e, "files", _manifests(e)[-1].get("files", [{}])[0].get("exists") is True)),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
        ],
    },
    {
        "name": "S03_failed_read_then_recover",
        "desc": "A failing tool (file missing) must not abort the turn; single failure recovers.",
        "scripts": [
            '```tool\n{"tool": "file_read", "params": {"path": "missing.txt"}}\n```',
            "The file is missing, nothing to do.",
        ],
        "checks": [
            ("failed tool_result emitted", lambda e, p, c: _require(e, "result", any(x.kind == EventKind.TOOL_RESULT and x.data.get("tool") == "file_read" and x.data.get("success") is False for x in e))),
            ("no REFLECTION_LIMIT", lambda e, p, c: _require(e, "limit", not any((x.data.get("code") or "") == "REFLECTION_LIMIT" for x in _errors(e)))),
            ("no errors at all", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S04_hallucinated_tool_ignored",
        "desc": "A non-registered tool is warned about and never executed; the turn recovers.",
        "scripts": [
            '```tool\n{"tool": "no_such_tool", "params": {"x": 1}}\n```',
            "All set.",
        ],
        "checks": [
            ("hallucinated warning once", lambda e, p, c: _require(e, "warning", sum(1 for m in _warnings(e) if "Hallucinated tools ignored" in m) == 1)),
            ("nothing executed", lambda e, p, c: _require(e, "executed", not any(x.kind in (EventKind.TOOL_CALL, EventKind.TOOL_RESULT) for x in e))),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S05_overwrite_denied",
        "desc": "auto_overwrite=False: write to an existing path is rejected and file is preserved.",
        "config": {"auto_overwrite": False},
        "prelude": "existing.txt:original",
        "scripts": [
            '```tool\n{"tool": "file_write", "params": {"path": "existing.txt", "content": "new"}}\n```',
            "Ok, leaving it as is.",
        ],
        "checks": [
            ("overwrite warning once", lambda e, p, c: _require(e, "warning", sum(1 for m in _warnings(e) if "File overwrite denied" in m) == 1)),
            ("file unchanged", lambda e, p, c: _require(e, "content", (Path(c.workspace_root) / "existing.txt").read_text(encoding="utf-8") == "original")),
            ("nothing executed", lambda e, p, c: _require(e, "executed", not any(x.kind == EventKind.TOOL_CALL for x in e))),
            ("manifest created empty", lambda e, p, c: _require(e, "created", _manifests(e)[-1].get("created") == [])),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S06_risky_command_denied",
        "desc": "auto_risky=False: a risky bash command is denied without executing bash.",
        "config": {"auto_risky": False},
        "scripts": [
            '```tool\n{"tool": "bash", "params": {"command": "rm -rf /tmp/x"}}\n```',
            "Fine, skipped.",
        ],
        "checks": [
            ("command denied warning once", lambda e, p, c: _require(e, "warning", sum(1 for m in _warnings(e) if "Command denied" in m) == 1)),
            ("no bash executed", lambda e, p, c: _require(e, "bash", not any(x.kind == EventKind.TOOL_CALL and x.data.get("tool") == "bash" for x in e))),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S07_delete_denied",
        "desc": "auto_risky=False: deleting a pre-existing file is denied and the file survives.",
        "config": {"auto_risky": False},
        "prelude": "victim.txt:data",
        "scripts": [
            '```tool\n{"tool": "file_delete", "params": {"path": "victim.txt"}}\n```',
            "Ok.",
        ],
        "checks": [
            ("delete denied warning once", lambda e, p, c: _require(e, "warning", sum(1 for m in _warnings(e) if "File delete denied" in m) == 1)),
            ("file survives", lambda e, p, c: _require(e, "file", (Path(c.workspace_root) / "victim.txt").exists())),
            ("nothing executed", lambda e, p, c: _require(e, "executed", not any(x.kind == EventKind.TOOL_CALL for x in e))),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S08_rewrite_blocked",
        "desc": "One-write-per-path: a second write to an already-written path is blocked, other new work runs.",
        "scripts": [
            '```tool\n{"tool": "file_write", "params": {"path": "a.txt", "content": "v1"}}\n{"tool": "file_write", "params": {"path": "a.txt", "content": "v2"}}\n```',
            "Done.",
        ],
        "checks": [
            ("first write wins", lambda e, p, c: _require(e, "content", (Path(c.workspace_root) / "a.txt").read_text(encoding="utf-8") == "v1")),
            ("rewrite blocked warning", lambda e, p, c: _require(e, "warning", _has_warning(e, "File rewrite blocked"))),
            ("only one execution", lambda e, p, c: _require(e, "executed", sum(1 for x in e if x.kind == EventKind.TOOL_CALL and x.data.get("tool") == "file_write") == 1)),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S09_stall_finalize",
        "desc": "Repeated identical call: executes once, warns once each, finalizes with stalled manifest.",
        "scripts": [
            ("Done. The file has been created successfully.\n```tool\n"
            '{"tool": "file_read", "params": {"path": "test.txt"}}\n```')
        ],
        "checks": [
            ("bounded calls", lambda e, p, c: _require(e, "calls", p.call_count <= 3)),
            ("skip warning exactly once", lambda e, p, c: _require(e, "skip", sum(1 for m in _warnings(e) if "Skipped calls already completed" in m) == 1)),
            ("stall guidance once", lambda e, p, c: _require(e, "stall", sum(1 for m in _warnings(e) if "No new tool was executed this iteration" in m) == 1)),
            ("finalize warning once", lambda e, p, c: _require(e, "finalize", sum(1 for m in _warnings(e) if "No new tool work for several consecutive iterations" in m) == 1)),
            ("manifest stalled", lambda e, p, c: _require(e, "stalled", _manifests(e)[-1].get("stalled") is True)),
            ("manifest remaining", lambda e, p, c: _require(e, "remaining", bool(_manifests(e)[-1].get("remaining")))),
            ("final answer once", lambda e, p, c: _require(e, "answer", len([t for t in _full_messages(e) if t.startswith("Done.")]) == 1)),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S10_empty_response",
        "desc": "A completely empty model response must surface EMPTY_RESPONSE as the terminal event.",
        "scripts": [""],
        "skip_invariants": True,
        "checks": [
            ("EMPTY_RESPONSE error present", lambda e, p, c: _require(e, "code", any((x.data.get("code") or "") == "EMPTY_RESPONSE" for x in _errors(e)))),
            ("error is recoverable+retry", lambda e, p, c: _require(e, "meta", all(x.data.get("recoverable") is True and x.data.get("action") == "retry" for x in _errors(e) if (x.data.get("code") or "") == "EMPTY_RESPONSE"))),
            ("no success banner", lambda e, p, c: _require(e, "no-success", not any(x.kind == EventKind.SUCCESS for x in e))),
            ("terminal event is the error", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.ERROR)),
        ],
    },
    {
        "name": "S11_provider_rate_limit",
        "desc": "A provider rate-limit error surfaces RATE_LIMIT, never a success banner.",
        "scripts": [{"raise": RateLimitError("daily quota", provider="dryrun", retry_after=3600, recoverable=False)}],
        "skip_invariants": True,
        "checks": [
            ("RATE_LIMIT error present", lambda e, p, c: _require(e, "code", any((x.data.get("code") or "") == "RATE_LIMIT" for x in _errors(e)))),
            ("no EMPTY_RESPONSE", lambda e, p, c: _require(e, "empty", not any((x.data.get("code") or "") == "EMPTY_RESPONSE" for x in _errors(e)))),
            ("no success banner", lambda e, p, c: _require(e, "no-success", not any(x.kind == EventKind.SUCCESS for x in e))),
            ("terminal event is the error", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.ERROR)),
        ],
    },
    {
        "name": "S12_length_finish_with_tool",
        "desc": "finish_reason=LENGTH interrupts a turn without executing its tool calls; the next STOP turn runs them. No LENGTH_EXCEEDED error.",
        "scripts": [
            {"text": "I'm starting...", "finish_reason": FinishReason.LENGTH},
            '```tool\n{"tool": "file_write", "params": {"path": "len.txt", "content": "ok"}}\n```',
            "Done.",
        ],
        "checks": [
            ("tool executed on following turn", lambda e, p, c: _require(e, "content", (Path(c.workspace_root) / "len.txt").read_text(encoding="utf-8") == "ok")),
            ("no LENGTH_EXCEEDED", lambda e, p, c: _require(e, "length", not any((x.data.get("code") or "") == "LENGTH_EXCEEDED" for x in _errors(e)))),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S13_plan_mode_read_only",
        "desc": "Plan mode: write tools are not offered; a direct write call cannot create files.",
        "mode": "plan",
        "prompt": "Analyze the project",
        "scripts": [
            '```tool\n{"tool": "file_write", "params": {"path": "p.txt", "content": "x"}}\n```',
            "Plan complete.",
        ],
        "checks": [
            ("no file created", lambda e, p, c: _require(e, "file", not (Path(c.workspace_root) / "p.txt").exists())),
            ("file_write not offered", lambda e, p, c: _require(e, "offered", p.offered_tools is not None and "file_write" not in p.offered_tools)),
            ("read tools offered", lambda e, p, c: _require(e, "read", "file_read" in (p.offered_tools or []))),
            ("write call blocked by mode gate", lambda e, p, c: _require(e, "gated", any(x.kind == EventKind.TOOL_RESULT and x.data.get("tool") == "file_write" and x.data.get("success") is False for x in e))),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S14_dynamic_tool_escalation",
        "desc": "A registered-but-unseeded tool (multi_edit) escalates and executes rather than being ignored.",
        "scripts": [
            '```tool\n{"tool": "multi_edit", "params": {"filepath": "ghost.txt", "edits": [{"old_content": "a", "new_content": "b"}]}}\n```',
            "Ok, file did not exist.",
        ],
        "checks": [
            ("multi_edit executed", lambda e, p, c: _require(e, "executed", any(x.kind == EventKind.TOOL_RESULT and x.data.get("tool") == "multi_edit" for x in e))),
            ("no hallucinated warning for multi_edit", lambda e, p, c: _require(e, "hallucinated", not any("Hallucinated tools ignored" in m and "multi_edit" in m for m in _warnings(e)))),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S15_big_read_compaction",
        "desc": "An oversized tool output is compacted and a context_compacted event is emitted.",
        "prelude": "big.txt:2000",
        "scripts": [
            '```tool\n{"tool": "file_read", "params": {"path": "big.txt"}}\n```',
            "The file is big; done.",
        ],
        "checks": [
            ("read succeeded", lambda e, p, c: _require(e, "read", any(x.kind == EventKind.TOOL_RESULT and x.data.get("tool") == "file_read" and x.data.get("success") for x in e))),
            ("context_compacted emitted", lambda e, p, c: _require(e, "compacted", any(x.kind == EventKind.CONTEXT_COMPACTED for x in e))),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S16_cancel_before_start",
        "desc": "A pre-cancelled request yields the pre-start cancellation warning and no success.",
        "cancel_before_start": True,
        "scripts": ["Hello"],
        "skip_invariants": True,
        "checks": [
            ("cancelled warning", lambda e, p, c: _require(e, "warning", _has_warning(e, "Request was cancelled before starting"))),
            ("no success", lambda e, p, c: _require(e, "no-success", not any(x.kind == EventKind.SUCCESS for x in e))),
        ],
    },
    {
        "name": "S17_cancel_mid_loop",
        "desc": "Cancelling mid-turn stops the loop at the next iteration boundary (top-of-loop cancel check).",
        "scripts": ['```tool\n{"tool": "file_read", "params": {"path": "test.txt"}}\n```', "More work later."],
        "cancel_after": 2,
        "skip_invariants": True,
        "checks": [
            ("cancelled warning", lambda e, p, c: _require(e, "warning", _has_warning(e, "Request cancelled"))),
            ("no success", lambda e, p, c: _require(e, "no-success", not any(x.kind == EventKind.SUCCESS for x in e))),
            ("no turn manifest", lambda e, p, c: _require(e, "manifest", not _manifests(e))),
            ("loop stopped before next turn", lambda e, p, c: _require(e, "calls", p.call_count <= 1)),
        ],
    },
    {
        "name": "S18_no_files_created_warning",
        "desc": "Build mode that used tools but wrote nothing emits the NO_FILES_CREATED warning.",
        "prelude": "readme.txt:hi",
        "scripts": [
            '```tool\n{"tool": "file_read", "params": {"path": "readme.txt"}}\n```',
            "I read the file.",
        ],
        "checks": [
            ("NO_FILES_CREATED warning", lambda e, p, c: _require(e, "warning", any((x.data.get("code") or "") == "NO_FILES_CREATED" for x in e if x.kind == EventKind.WARNING))),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S19_lint_warning_on_python",
        "desc": "Writing a Python file with an unfixable lint error triggers the post-execution lint hook warning with code=LINT.",
        "scripts": [
            '```tool\n{"tool": "file_write", "params": {"path": "bad.py", "content": "def foo():\\n    return missing_symbol\\n"}}\n```',
            "Done.",
        ],
        "checks": [
            ("lint warning emitted", lambda e, p, c: _require(e, "lint", _has_warning(e, "Lint issues detected"))),
            ("lint warning carries LINT code", lambda e, p, c: _require(e, "code", any((x.data.get("code") or "") == "LINT" and "Lint issues detected" in (x.data.get("message") or "") for x in e if x.kind == EventKind.WARNING))),
            ("file written anyway", lambda e, p, c: _require(e, "file", (Path(c.workspace_root) / "bad.py").exists())),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S20_lint_auto_fix",
        "desc": "A fixable lint issue is auto-fixed by the post-execution hook, so no lint warning is emitted.",
        "scripts": [
            '```tool\n{"tool": "file_write", "params": {"path": "fixable.py", "content": "import math\\nprint(\\"hi\\")\\n"}}\n```',
            "Done.",
        ],
        "checks": [
            ("no lint warning emitted", lambda e, p, c: _require(e, "lint", not _has_warning(e, "Lint issues detected"))),
            ("file written anyway", lambda e, p, c: _require(e, "file", (Path(c.workspace_root) / "fixable.py").exists())),
            ("auto-fix removed unused import", lambda e, p, c: _require(e, "fixed", "import math" not in (Path(c.workspace_root) / "fixable.py").read_text(encoding="utf-8"))),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S21_write_unverified",
        "desc": "Files written with no successful tool after them are reported as not verified in the manifest and success message.",
        "scripts": [
            '```tool\n{"tool": "file_write", "params": {"path": "good.py", "content": "print(\\"hi\\")\\n"}}\n```',
            "Done.",
        ],
        "checks": [
            ("unverified note in success", lambda e, p, c: _require(e, "unverified", any(x.kind == EventKind.SUCCESS and "Files changed but not verified" in (x.data.get("message") or "") for x in e))),
            ("manifest verified false", lambda e, p, c: _require(e, "verified", _manifests(e)[-1].get("verified") is False)),
            ("manifest checks empty", lambda e, p, c: _require(e, "checks", _manifests(e)[-1].get("checks") == [])),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S22_write_then_read_verified",
        "desc": "A successful read with output after a write marks the manifest verified and drops the unverified note.",
        "scripts": [
            '```tool\n{"tool": "file_write", "params": {"path": "good.py", "content": "print(\\"hi\\")\\n"}}\n{"tool": "file_read", "params": {"path": "good.py"}}\n```',
            "Verified it.",
        ],
        "checks": [
            ("manifest verified true", lambda e, p, c: _require(e, "verified", _manifests(e)[-1].get("verified") is True)),
            ("read recorded as check", lambda e, p, c: _require(e, "check", any(c.get("tool") == "file_read" for c in _manifests(e)[-1].get("checks", [])))),
            ("no unverified note", lambda e, p, c: _require(e, "no-unverified", not any(x.kind == EventKind.SUCCESS and "Files changed but not verified" in (x.data.get("message") or "") for x in e))),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S24_edit_then_verify_completes_without_stall",
        "desc": "Task 13 A3/RC5: file changes that landed AND a successful tool that produced observable output AFTER the last change are a legitimate completion — the turn must report completed=True, stalled=False, remaining=[] even though the model wrote no closing prose and then repeated a call.",
        "scripts": [
            '```tool\n{"tool": "file_write", "params": {"path": "good.py", "content": "x = 1\\n"}}\n{"tool": "file_edit", "params": {"path": "good.py", "old_content": "x = 1", "new_content": "x = 2"}}\n{"tool": "bash", "params": {"command": "echo verified"}}\n```',
            '```tool\n{"tool": "bash", "params": {"command": "echo verified"}}\n```',
            "All done.",
        ],
        "checks": [
            ("manifest completed", lambda e, p, c: _require(e, "completed", _manifests(e)[-1].get("completed") is True)),
            ("manifest not stalled", lambda e, p, c: _require(e, "stalled", _manifests(e)[-1].get("stalled") is False)),
            ("no remaining work", lambda e, p, c: _require(e, "remaining", _manifests(e)[-1].get("remaining") == [])),
            ("verified via evidence", lambda e, p, c: _require(e, "verified", _manifests(e)[-1].get("verified") is True)),
            ("created file reflects the edit", lambda e, p, c: _require(e, "content", "good.py" in _manifests(e)[-1].get("created", []) and (Path(c.workspace_root) / "good.py").read_text(encoding="utf-8") == "x = 2\n")),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
    {
        "name": "S23_background_completion_surfaced",
        "desc": "A background job that finishes during the turn surfaces a BACKGROUND_COMPLETED warning at the next iteration boundary.",
        "prelude": "bg.py:marker",
        "scripts": [
            '```tool\n{"tool": "bash", "params": {"command": "' + _PY + ' bg.py", "run_in_background": true}}\n```',
            '```tool\n{"tool": "bash", "params": {"command": "' + _PY + ' bg.py"}}\n```',
            "All done.",
        ],
        "checks": [
            ("BACKGROUND_COMPLETED warning", lambda e, p, c: _require(e, "bg", any((x.data.get("code") or "") == "BACKGROUND_COMPLETED" for x in e if x.kind == EventKind.WARNING))),
            ("warning names the job", lambda e, p, c: _require(e, "job", any("Background job" in (x.data.get("message") or "") for x in e if (x.data.get("code") or "") == "BACKGROUND_COMPLETED"))),
            ("background job actually started", lambda e, p, c: _require(e, "bg-job", any(x.kind == EventKind.TOOL_RESULT and x.data.get("tool") == "bash" and "Background job started" in (x.data.get("output") or "") for x in e))),
            ("no errors", lambda e, p, c: _require(e, "errors", not _errors(e))),
            ("terminal success", lambda e, p, c: _require(e, "terminal", e[-1].kind == EventKind.SUCCESS)),
        ],
    },
]


# ---------------------------------------------------------------------------
# Matrix runner
# ---------------------------------------------------------------------------


async def _prelude(config: AppSettings, spec: str | None) -> None:
    if not spec:
        return
    kind, _, rest = spec.partition(":")
    ws = Path(config.workspace_root)
    if kind == "existing.txt":
        (ws / "existing.txt").write_text(rest, encoding="utf-8")
    elif kind == "victim.txt":
        (ws / "victim.txt").write_text(rest, encoding="utf-8")
    elif kind == "readme.txt":
        (ws / "readme.txt").write_text(rest, encoding="utf-8")
    elif kind == "big.txt":
        count = int(rest)
        content = "\n".join(f"line {i} of content to pad the read output significantly" for i in range(count))
        (ws / "big.txt").write_text(content + "\n", encoding="utf-8")
    elif kind == "bg.py":
        (ws / "bg.py").write_text(
            "import time\ntime.sleep(1.2)\nprint('bg-done')\n", encoding="utf-8"
        )


async def _run_scenario(scenario: dict, temp_dir: Path) -> tuple[list[str], dict]:
    failures: list[str] = []
    config = _config(temp_dir, **scenario.get("config", {}))
    await _prelude(config, scenario.get("prelude"))
    provider = _DryRunProvider(scenario["scripts"])

    if scenario.get("cancel_before_start"):
        agent = AgentLoop(config, provider, tool_registry=create_default_registry())
        agent._cancel_sequence = 10**9  # simulate a cancel that already happened
        events = [ev async for ev in agent.process_prompt(scenario.get("prompt", "Do the work"), "s1", [], scenario.get("mode", "build"))]
    else:
        events = await _run(
            provider,
            config,
            mode=scenario.get("mode", "build"),
            prompt=scenario.get("prompt", "Do the work"),
            cancel_after=scenario.get("cancel_after"),
        )

    for desc, fn in scenario["checks"]:
        try:
            fn(events, provider, config)
        except AssertionError as exc:
            failures.append(f"FAIL [{desc}]: {exc}")
    if not scenario.get("skip_invariants"):
        try:
            _check_global_invariants(events)
        except AssertionError as exc:
            failures.append(f"FAIL [invariant]: {exc}")
    summary = {
        "name": scenario["name"],
        "events": len(events),
        "kinds": [str(e.kind) for e in events],
    }
    return failures, summary


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
async def test_dryrun_scenario(scenario, temp_dir):
    failures, summary = await _run_scenario(scenario, temp_dir)
    assert not failures, (
        f"{scenario['name']} failed ({summary['events']} events):\n" + "\n".join(failures)
    )


# ---------------------------------------------------------------------------
# Unit-level dry run of the loop's pure helpers
# ---------------------------------------------------------------------------


class TestLoopHelperDryRun:
    def test_call_signature_is_stable(self):
        a = _call_signature("file_write", {"path": "b.txt", "content": "x"})
        b = _call_signature("file_write", {"content": "x", "path": "b.txt"})
        assert a == b, "signature must ignore param dict ordering"

    def test_all_calls_repeat(self):
        sig = ("file_read", '{"path":"a.txt"}')
        assert _all_calls_repeat([], {sig}) is False
        call = {"tool": "file_read", "params": {"path": "a.txt"}}
        assert _all_calls_repeat([call], {sig}) is True
        call2 = {"tool": "file_read", "params": {"path": "b.txt"}}
        assert _all_calls_repeat([call, call2], {sig}) is False

    def test_params_label(self):
        assert _params_label({}) == ""
        assert _params_label({"path": "app/main.py", "content": "x"}) == "path=app/main.py"
        assert _params_label({"tool_name": "todo"}) == "todo"
        assert _params_label({"command": "x" * 100}).startswith("command=")

    def test_most_common_count(self):
        assert _most_common_count([]) == 0
        assert _most_common_count(["a", "b", "a"]) == 2

    def test_build_manifest(self, temp_dir):
        ws = str(temp_dir)
        (temp_dir / "made.txt").write_text("x", encoding="utf-8")
        m = _build_manifest({"made.txt"}, ["made.txt"], True, False, "done", ws)
        assert m["completed"] is True and m["stalled"] is False
        assert m["created"] == ["made.txt"] and m["remaining"] == []
        assert m["files"] == [{"path": "made.txt", "exists": True, "size": 1}]
        m2 = _build_manifest({"made.txt"}, [], False, True, "stuck", ws)
        assert m2["completed"] is False and m2["stalled"] is True
        assert m2["remaining"] == ["stuck"]

    def test_build_manifest_verification_flag(self, temp_dir):
        ws = str(temp_dir)
        (temp_dir / "a.txt").write_text("a", encoding="utf-8")
        # No files changed: verified defaults to True (nothing to verify).
        empty = _build_manifest(set(), [], True, False, "done", ws)
        assert empty["verified"] is True and empty["checks"] == []
        # Files created but nothing ran after them: not verified.
        unverified = _build_manifest({"a.txt"}, ["a.txt"], True, False, "done", ws)
        assert unverified["verified"] is False and unverified["checks"] == []
        # A post-change tool that produced observable output marks the turn verified.
        verified = _build_manifest(
            {"a.txt"}, ["a.txt"], True, False, "done", ws,
            verification=[{"tool": "file_read", "output_len": 12}],
        )
        assert verified["verified"] is True
        assert verified["checks"] == [{"tool": "file_read", "output_len": 12}]
        # A successful tool with NO output bytes is not evidence of a working change.
        silent = _build_manifest(
            {"a.txt"}, ["a.txt"], True, False, "done", ws,
            verification=[{"tool": "bash", "output_len": 0, "exit_code": 0}],
        )
        assert silent["verified"] is False
        assert silent["checks"] == [{"tool": "bash", "output_len": 0, "exit_code": 0}]
        # Internal sequence keys never leak into the manifest checks list.
        stripped = _build_manifest(
            {"a.txt"}, ["a.txt"], True, False, "done", ws,
            verification=[{"tool": "bash", "output_len": 5, "seq": 3}],
        )
        assert stripped["checks"] == [{"tool": "bash", "output_len": 5}]

    def test_has_verification_evidence(self):
        # Empty or no checks: never evidence.
        assert _has_verification_evidence([]) is False
        assert _has_verification_evidence(None) is False
        # Output bytes are evidence.
        assert _has_verification_evidence([{"tool": "bash", "output_len": 12}]) is True
        # Zero-output success is not evidence.
        assert _has_verification_evidence([{"tool": "bash", "output_len": 0, "exit_code": 0}]) is False
        # after_seq: a check recorded before the last change does not verify it.
        checks = [{"tool": "bash", "output_len": 12, "seq": 1}, {"tool": "bash", "output_len": 3, "seq": 2}]
        assert _has_verification_evidence(checks, after_seq=2) is True
        assert _has_verification_evidence([{"tool": "bash", "output_len": 12, "seq": 1}], after_seq=2) is False

    def test_find_compaction_cut_and_group(self):
        def m(role, content=""):
            return SimpleNamespace(role=role, content=content)

        hist = [m("user"), m("assistant"), m("tool"), m("tool")]
        # Group starts at the assistant message that issued the tool calls.
        assert _group_start(hist, 4) == 1
        hist2 = [m("user", "a"), m("assistant", "b"), m("tool", "c"), m("tool", "d")]
        # Cutting must not split the assistant+tool group: keep_tail=2 still
        # keeps the [assistant, tool, tool] group, so only the first message drops.
        assert _find_compaction_cut(hist2, keep_tail=2) == 1
        hist3 = [m("user", "x")] * 20
        assert _find_compaction_cut_budgeted(hist3, 3, lambda c: 1) == 17

    def test_reflection_error_limit_windows(self):
        assert reflection_error_limit(32000) == 3
        assert reflection_error_limit(128000) == 4
        assert reflection_error_limit(32000 + 64000 * 20) <= 20

    def test_dynamic_max_output_tiers(self):
        assert _dynamic_max_output(128000) == 15_000
        assert _dynamic_max_output(200_000) == 25_000
        assert _dynamic_max_output(1_000_000) == 50_000
        assert _dynamic_max_output(1000) == 10_000

    def test_compact_tool_output_trims(self):
        text = "x" * 300
        compacted, stats = compact_tool_output(text, max_output=100)
        assert stats.original_chars == 300
        assert stats.trimmed is True
        assert stats.chars_removed == len(text) - len(compacted), (
            "chars_removed must equal original minus compacted length"
        )
        assert len(compacted) < len(text), "compaction must shrink the output"
        assert "truncated" in compacted, "compacted output carries the truncation marker"
        assert len(compacted) < 300, "compacted output must be shorter than the original"

    def test_head_tail_trim(self):
        trimmed, omitted = head_tail_trim("a" * 100, 40)
        assert omitted == 60
        assert len(trimmed) < 100, "trimmed output must be shorter than the original"


class TestCommandSafetyDryRun:
    def test_risky_recursive_delete(self):
        assert assess_command("rm -rf /tmp/x").is_risky
        assert assess_command("rm -rf /tmp/x").risk_level == "high"

    def test_banned_command(self):
        assert is_command_banned("sudo") is not None

    def test_safe_command(self):
        assert assess_command("ls -la").is_risky is False


class TestValidationDryRun:
    def test_validate_tool_calls_splits(self):
        valid, invalid = validate_tool_calls(
            [
                {"tool": "file_read", "params": {}},
                {"tool": "phantom", "params": {}},
            ],
            {"file_read"},
        )
        assert [t["tool"] for t in valid] == ["file_read"]
        assert [t["tool"] for t in invalid] == ["phantom"]

    def test_validate_tool_rejection_placeholder(self):
        msg = validate_tool_rejection("file_write", {"path": "x.txt", "content": "[PASTE]"}, set(), ".")
        assert msg and "placeholder" in msg.lower()

    def test_validate_tool_rejection_self_delete(self):
        msg = validate_tool_rejection("file_delete", {"path": "made.txt"}, {"made.txt"}, ".")
        assert msg and "delete" in msg.lower()


class TestParserDryRun:
    def test_parse_single_tool_fence(self):
        clean, calls = UnifiedResponseFormatter.process_response(
            'Do it.\n```tool\n{"tool": "file_write", "params": {"path": "a.txt", "content": "x"}}\n```'
        )
        assert clean == "Do it."
        assert len(calls) == 1 and calls[0]["tool"] == "file_write"

    def test_parse_multiple_tool_fences(self):
        _, calls = UnifiedResponseFormatter.process_response(
            '```tool\n{"tool": "file_write", "params": {"path": "a.txt", "content": "x"}}\n```\n'
            '```tool\n{"tool": "file_read", "params": {"path": "b.txt"}}\n```'
        )
        assert [c["tool"] for c in calls] == ["file_write", "file_read"]

    def test_parse_malformed_json_does_not_crash(self):
        # A truncated/ungrammatical fence must never raise; the parser either
        # repairs it or falls back to clean text with no calls.
        clean, calls = UnifiedResponseFormatter.process_response(
            '```tool\n{"tool": "file_write", "params": {"path": '
        )
        assert isinstance(clean, str)
        assert isinstance(calls, list)

    def test_schemas_to_openai_tools(self):
        schemas = [{"name": "file_read", "description": "d", "schema": {"type": "object"}}]
        tools = schemas_to_openai_tools(schemas)
        assert tools[0]["function"]["name"] == "file_read"


class TestDurableReplayAcrossTurns:
    """Task 13 A2: byte-identical writes re-emitted in a LATER turn of the same
    session are blocked; a build must never run twice and a manifest must never
    claim a re-creation."""

    async def test_repeated_prompt_does_not_rebuild(self, temp_dir):
        session_id = "s-replay-1"
        reset_session(session_id)
        config = _config(temp_dir)

        # Turn 1: the model writes a.py, reads it back (evidence), and reports done.
        first = _DryRunProvider(
            [
                ('```tool\n{"tool": "file_write", "params": {"path": "a.py", "content": "x = 1\\n"}}\n'
                '{"tool": "file_read", "params": {"path": "a.py"}}\n```'),
                "Done.",
            ]
        )
        evs1 = await _run(first, config, prompt="Build a thing", session_id=session_id)
        m1 = _manifests(evs1)[-1]
        assert m1["created"] == ["a.py"]
        assert (temp_dir / "a.py").read_text(encoding="utf-8") == "x = 1\n"
        first_writes = _tool_runs(evs1, "file_write")

        # Turn 2 (same session): the model "rebuilds" by re-emitting the exact
        # same write. The durable guard must block it, so a.py stays untouched and
        # the manifest reports no creation.
        second = _DryRunProvider(
            [
                ('```tool\n{"tool": "file_write", "params": {"path": "a.py", "content": "x = 1\\n"}}\n'
                '{"tool": "file_read", "params": {"path": "a.py"}}\n```'),
                "Done.",
            ]
        )
        evs2 = await _run(
            second, config, prompt="Rebuild it", session_id=session_id, reset_registry=False
        )
        m2 = _manifests(evs2)[-1]
        assert m2["created"] == []
        assert m2["modified"] == []
        second_writes = _tool_runs(evs2, "file_write")
        assert second_writes == 0
        assert first_writes == 1
        assert (temp_dir / "a.py").read_text(encoding="utf-8") == "x = 1\n"
        # The block is surfaced so the model knows why nothing happened.
        assert any("re-write blocked" in (x.data.get("message") or "").lower() for x in evs2 if x.kind == EventKind.WARNING)

    async def test_new_session_is_not_blocked(self, temp_dir):
        session_id = "s-replay-2"
        reset_session(session_id)
        provider = _DryRunProvider(
            [
                '```tool\n{"tool": "file_write", "params": {"path": "b.py", "content": "y = 2\\n"}}\n```',
                "Done.",
            ]
        )
        evs = await _run(provider, _config(temp_dir), prompt="Build b", session_id=session_id)
        assert _manifests(evs)[-1]["created"] == ["b.py"]
        assert (temp_dir / "b.py").read_text(encoding="utf-8") == "y = 2\n"


def _tool_runs(events, tool_name) -> int:
    # Blocked/rejected calls never emit a TOOL_CALL, so counting TOOL_CALL
    # events equals actual executions.
    return sum(
        1 for ev in events if ev.kind == EventKind.TOOL_CALL and ev.data.get("tool") == tool_name
    )

