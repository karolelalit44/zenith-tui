"""All-tools smoke test: verify every registered tool end-to-end.

Boots the real backend and the real TUI in a visible winpty console (the same
environment as ``smoke_tui_session.py``) and runs two turns:

Turn 1 — tool inventory
    Asks the model to enumerate every capability/tool via ``discover_capabilities``
    and to load a schema via ``get_tool_definition``. The final answer is saved
    to ``zenith-artifacts/turn1_tool_inventory/report.txt``.

Turn 2 — multi-tool exercise
    Drives the model through one operation per tool, inside
    ``zenith-artifacts/turn2_tool_exercise/``. The 18-step exercise is split into
    focused sub-turns so each stays small enough for a replay-heavy model to
    complete in a single pass:

    bash / file_write / file_edit / multi_edit / file_read / grep / glob / todo /
    background (bash run_in_background) / job_output / job_kill / agent /
    webfetch / lsp_definition / lsp_diagnostics / lsp_rename / file_delete

    Every artifact the model writes lands in the turn2 folder so the sub-turns
    stay isolated. The LSP tools are environment-dependent (they need an LSP
    server for the language); the script records their outcome but does not
    hard-fail on "no LSP server" — it only fails if they are never invoked.

Usage::

    .venv\\Scripts\\python.exe scripts/smoke_tool_exercise.py [--turn-timeout 600]

Env overrides (optional, same as smoke_tui_session.py):
    SMOKE_BACKEND_WAIT / SMOKE_TUI_READY_WAIT / SMOKE_SESSION_WAIT
    SMOKE_TURN_TIMEOUT / SMOKE_TYPE_DELAY_MS / SMOKE_TURN_GAP_S
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from smoke_tui_session import (
    TURN_GAP_S,
    PtyLog,
    RpcClient,
    _cleanup,
    _enum_console_windows,
    _log_tui_tail,
    _resolve_tui_argv,
    _wait_tui_ready,
    get_free_port,
    pty_reader,
    show_tui_window,
    spawn_backend,
    strip_ansi,
    summarize_turn,
    type_text,
    wait_for_session,
    wait_for_turn_end,
    wait_health,
)

try:
    from websockets.asyncio.client import connect as ws_connect
except ImportError:
    from websockets.client import connect as ws_connect

try:
    from winpty import Backend, PtyProcess
except ImportError:
    from winpty import PtyProcess

    Backend = None

ROOT = Path(__file__).resolve().parent.parent
PASS = "PASS"
FAIL = "FAIL"

ARTIFACTS_ROOT = ROOT / "zenith-artifacts"
TURN1_DIR = ARTIFACTS_ROOT / "turn1_tool_inventory"
TURN2_DIR = ARTIFACTS_ROOT / "turn2_tool_exercise"

_pty_log: PtyLog | None = None

EMPTY_SUMMARY = {"tools": [], "iterations": 0, "warnings": [], "message": ""}

# Tools the multi-tool exercise must invoke (tool_call event observed).
REQUIRED_TOOLS = {
    "bash",
    "file_write",
    "file_read",
    "file_edit",
    "multi_edit",
    "grep",
    "glob",
    "todo",
    "job_output",
    "job_kill",
    "agent",
    "webfetch",
    "file_delete",
}
# Environment-dependent: must be invoked, but outcome is informational.
LSP_TOOLS = {"lsp_definition", "lsp_diagnostics", "lsp_rename"}

# (relative path in turn2 dir, expected exact content after strip(), message)
ARTIFACT_EXPECTATIONS = [
    ("from_bash.txt", "written via bash", "bash file write"),
    ("source.txt", "alpha-one\nB\ngamma-three", "file_write + file_edit + multi_edit"),
    ("bg_result.txt", "background ok", "background job output"),
    ("subagent_result.txt", "sub-agent ok", "sub-agent delegated write"),
]
OPTIONAL_ARTIFACTS = [
    "fetched.txt",  # webfetch -> /health body saved by the model
    "lsp_result.txt",  # lsp results (if any) saved by the model
]
DELETED_ARTIFACT = "temp_delete.txt"


def _prepare_artifacts() -> None:
    """Reset the artifact tree so each run starts clean."""
    shutil.rmtree(ARTIFACTS_ROOT, ignore_errors=True)
    TURN1_DIR.mkdir(parents=True, exist_ok=True)
    TURN2_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[tools] artifacts -> {ARTIFACTS_ROOT.relative_to(ROOT)}")
    print(f"[tools]   turn 1   -> {TURN1_DIR.relative_to(ROOT)}")
    print(f"[tools]   turn 2   -> {TURN2_DIR.relative_to(ROOT)}")


def _read_stripped(rel: str) -> str:
    path = TURN2_DIR / rel
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


# ── Composer idle / banner helpers (mirror smoke_confirm_flow.py) ─────────────

_COMPOSER_HINTS = (
    "Ask anything",
    "Describe the change",
    "@ file · / cmd · ? help",
    "Choose an action above",
)
_IDLE_HINTS = ("Ask anything", "Describe the change", "@ file · / cmd · ? help")


def _recent_tail(log: PtyLog, n: int = 20_000) -> str:
    text = log.text()
    return text[-n:] if len(text) > n else text


def _tail_text(log: PtyLog, n: int = 30_000) -> str:
    return strip_ansi(_recent_tail(log, n))


def _composer_hint(log: PtyLog) -> str:
    t = strip_ansi(_recent_tail(log))
    hint, pos = "", -1
    for candidate in _COMPOSER_HINTS:
        at = t.rfind(candidate)
        if at > pos:
            pos, hint = at, candidate
    return hint


def _banner_is_up(log: PtyLog) -> bool:
    return _composer_hint(log) == "Choose an action above" and "Task failed" in strip_ansi(
        _recent_tail(log)
    )


def _composer_idle(log: PtyLog) -> bool:
    t = strip_ansi(_recent_tail(log))
    hint = _composer_hint(log)
    return hint in _IDLE_HINTS and t.rfind(hint) > t.rfind("Working")


async def _wait_idle(log: PtyLog, timeout: int = 30) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _composer_idle(log):
            return True
        await asyncio.sleep(0.5)
    return False


def _composer_empty(log: PtyLog) -> bool:
    bottom = _tail_text(log, 1600)
    return any(h in bottom for h in _IDLE_HINTS) and "Choose an action above" not in bottom


async def _composer_shows(log: PtyLog, needle: str, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if needle in _tail_text(log):
            return True
        await asyncio.sleep(0.25)
    return False


async def _type_verified(pty, log: PtyLog, text: str) -> bool:
    if pty is None or not pty.isalive():
        return False
    print("[tools]   writing prompt to composer...")
    pty.write(text)
    ok = await _composer_shows(log, text[:40], timeout=20.0)
    if ok:
        await asyncio.sleep(1.5)
    else:
        print(
            "[tools]   warning: prompt echo not detected in composer; submitting anyway (export check gates it)"
        )
        await asyncio.sleep(3.0)
    pty.write("\r")
    return True


async def _prompt_landed_verified(
    rpc: RpcClient, session_id: str, marker: str, timeout: float = 45.0
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            res = await rpc.call("session.export", {"session_id": session_id}, timeout=30)
            markdown = (res or {}).get("markdown", "") if res else ""
        except Exception:
            markdown = ""
        if marker in markdown:
            return True
        await asyncio.sleep(1)
    return False


async def _dismiss_retry_banner(log: PtyLog, pty) -> None:
    if pty is None or not pty.isalive():
        return
    deadline = time.monotonic() + 25.0
    while time.monotonic() < deadline and not _banner_is_up(log):
        await asyncio.sleep(0.25)
    if not _banner_is_up(log):
        return
    for _ in range(4):
        if not _banner_is_up(log):
            return
        pty.write("\x1b")
        await asyncio.sleep(0.8)


async def _finish_turn(status: str, pty) -> None:
    if status not in ("success", "timeout"):
        await _dismiss_retry_banner(_pty_log, pty)
        _log_tui_tail(_pty_log, name="after retry dismiss")
    await _wait_idle(_pty_log)
    await asyncio.sleep(2.0)


# ── Turn helpers ──────────────────────────────────────────────────────────────


def _report(name: str, checks: list[tuple[str, bool]], detail: str = "") -> int:
    failures = 0
    print(f"\n[tools] --- {name} ---")
    for label, ok in checks:
        print(f"    [{PASS if ok else FAIL}] {label}")
        if not ok:
            failures += 1
    if detail:
        print(f"    detail: {detail}")
    return failures


async def _run_turn(
    name: str,
    ws,
    rpc: RpcClient,
    session_id: str,
    base_seq: int,
    prompt: str,
    marker: str,
    pty,
    turn_timeout: int,
) -> tuple[str, dict, int]:
    print(f"\n[tools] === {name} ===")
    if not await _wait_idle(_pty_log):
        raise RuntimeError(f"{name}: composer not idle before typing; refusing to type")
    print(f"[tools] typing: {prompt[:140]}...")
    if not await _type_verified(pty, _pty_log, prompt):
        _log_tui_tail(_pty_log, name=f"on {name} prompt echo failure")
        return "error", EMPTY_SUMMARY, base_seq
    if not await _prompt_landed_verified(rpc, session_id, marker):
        print(f"[tools]   {name}: full prompt text not confirmed in session (prompt did not land)")
        _log_tui_tail(_pty_log, name=f"on {name} prompt not landed")
        return "error", EMPTY_SUMMARY, base_seq
    print("[tools]   prompt landed (full text verified in session export)")
    try:
        status, events, _terminal, seen_seq = await wait_for_turn_end(
            rpc, session_id, base_seq, pty, turn_timeout
        )
    except TimeoutError as exc:
        print(f"[tools]   {name}: TIMEOUT ({exc})")
        _log_tui_tail(_pty_log, name=f"on {name} timeout")
        return "timeout", EMPTY_SUMMARY, base_seq
    summary = summarize_turn(events)
    print(f"[tools]   status={status} iterations={summary['iterations']}")
    print(f"[tools]   tools={summary['tools'] or 'none'}")
    for w in summary["warnings"]:
        print(f"[tools]   warning: {w}")
    print(f"[tools]   final message: {summary['message'] or '(empty)'}")
    return status, summary, seen_seq


def _tool_result_map(summary: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for tr in summary.get("all_tool_results", []):
        out[tr.get("tool", "")] = tr
    return out


# ── Phase 1: tool inventory ───────────────────────────────────────────────────

TOOL_INVENTORY_PROMPT = (
    "This is a TOOL INVENTORY verification turn. "
    "Step 1: call the tool discover_capabilities exactly once to enumerate every "
    "capability and every tool available to you. "
    "Step 2: call the tool get_tool_definition exactly once, for the tool named "
    "'file_write', to load its schema. "
    "Step 3: after both tool calls succeed, write a short markdown report naming "
    "the total number of capabilities you discovered and listing at least five "
    "example tool names you saw. "
    "Then STOP. Do NOT call any tool again, do not repeat the report, do not "
    "create any files, and do not call discover_capabilities or "
    "get_tool_definition a second time. Your final message must be plain text "
    "with no tool calls."
)


async def phase_inventory(
    ws,
    rpc: RpcClient,
    session_id: str,
    base_seq: int,
    pty,
    turn_timeout: int,
) -> tuple[int, int]:
    status, summary, seen_seq = await _run_turn(
        "1. TOOL INVENTORY",
        ws,
        rpc,
        session_id,
        base_seq,
        TOOL_INVENTORY_PROMPT,
        "get_tool_definition a second time",
        pty,
        turn_timeout,
    )
    report_path = TURN1_DIR / "report.txt"
    report_path.write_text(summary.get("message", "").strip(), encoding="utf-8")
    report_ok = report_path.exists() and report_path.stat().st_size > 0
    checks = [
        ("discover_capabilities was invoked", "discover_capabilities" in summary["tools"]),
        ("get_tool_definition was invoked", "get_tool_definition" in summary["tools"]),
        ("report.txt written", report_ok),
        ("turn completed cleanly (no timeout)", status != "timeout"),
    ]
    failures = _report(
        "1. TOOL INVENTORY",
        checks,
        f"tools={summary['tools'] or 'none'} report_bytes={report_path.stat().st_size if report_path.exists() else 0}",
    )
    await _finish_turn(status, pty)
    return failures, seen_seq


# ── Phase 2: multi-tool exercise ──────────────────────────────────────────────


# The 18-step exercise is split into focused sub-turns so each stays small enough
# for a replay-heavy model to complete in a single pass. Every tool is still
# exercised end-to-end through the real TUI/backend; the checks aggregate across
# all sub-turns.
EXERCISE_TURNS = [
    {
        "name": "2. FILE OPERATIONS",
        "marker": "use file_read to read source.txt",
        "steps": [
            (
                "use bash to ensure the directory exists by running exactly: "
                "mkdir zenith-artifacts/turn2_tool_exercise -Force"
            ),
            (
                "use bash to write the file from_bash.txt inside that directory with exactly "
                "the content 'written via bash', by running exactly: "
                "Set-Content -Path 'zenith-artifacts/turn2_tool_exercise/from_bash.txt' "
                "-Value 'written via bash' -NoNewline"
            ),
            (
                "use file_write to create source.txt inside the directory with the exact "
                "content of the three lines alpha, beta, gamma with no trailing newline"
            ),
            "use file_edit on source.txt replacing exactly 'beta' with 'B'",
            (
                "use multi_edit on source.txt with two edits: replace 'alpha' with "
                "'alpha-one' and replace 'gamma' with 'gamma-three'"
            ),
            "use file_read to read source.txt and report its content",
        ],
    },
    {
        "name": "3. SEARCH & TRACKING",
        "marker": "list the tasks",
        "steps": [
            (
                "use grep to search for 'alpha-one' inside zenith-artifacts/turn2_tool_exercise "
                "and report the matches"
            ),
            (
                "use glob to list the files under zenith-artifacts/turn2_tool_exercise and "
                "report them"
            ),
            (
                "use the todo tool to add the task 'write source file' and add the task "
                "'verify tools', then list the tasks"
            ),
        ],
    },
    {
        "name": "4. BACKGROUND JOBS",
        "marker": "terminate it by id",
        "steps": [
            (
                "use bash with run_in_background set to true to start this job, which after a "
                "short delay writes bg_result.txt inside the directory with content "
                "'background ok'. On Windows the background shell is cmd.exe, so run exactly "
                "this cmd command (do not convert it): ping -n 3 127.0.0.1 >nul & (echo "
                "background ok) > zenith-artifacts/turn2_tool_exercise/bg_result.txt. Then use "
                "job_output with that job's id to read its output"
            ),
            (
                "use bash with run_in_background set to true to start this long-running "
                "background job (cmd syntax, do not convert): ping -n 300 127.0.0.1 >nul. "
                "Then use job_kill to terminate it by id"
            ),
        ],
    },
    {
        "name": "5. DELEGATION & WEB",
        "marker": "fetched.txt",
        "steps": [
            (
                "use the agent tool to delegate a sub-agent whose task is: create the file "
                "zenith-artifacts/turn2_tool_exercise/subagent_result.txt containing exactly "
                "the single line sub-agent ok, and report the result"
            ),
            (
                "use webfetch to fetch this URL and then use file_write to save the fetched "
                "response body into fetched.txt inside the directory: http://127.0.0.1:{port}/health"
            ),
        ],
    },
    {
        "name": "6. LSP & DELETE",
        "marker": "delete temp_delete.txt",
        "steps": [
            (
                "use file_write to create sample.py inside the directory containing a function "
                "greet defined as: def greet():  then the line:     return 42, and below it a "
                "call site: greet()"
            ),
            (
                "use lsp_definition on sample.py at the line and column where 'greet' is "
                "defined, then use lsp_diagnostics on sample.py, then use lsp_rename to rename "
                "'greet' to 'hello'. If any of these LSP tools reports that no LSP server is "
                "available, record that and continue; use file_write to save whatever results "
                "you got into lsp_result.txt inside the directory"
            ),
            (
                "use file_write to create temp_delete.txt inside the directory with content "
                "'to be deleted'"
            ),
            "use file_delete to delete temp_delete.txt",
        ],
    },
]


def build_exercise_turn_prompt(part: int, total: int, port: int) -> str:
    spec = EXERCISE_TURNS[part - 1]
    step_list = " ".join(spec["steps"])
    return (
        f"This is MULTI-TOOL EXERCISE verification turn PART {part} of {total}. Work "
        "inside the directory zenith-artifacts/turn2_tool_exercise. If you need a tool "
        "you have not loaded yet, first call get_tool_definition to load it, then use "
        "it. Complete exactly these steps in this turn only: "
        + step_list
        + ". After completing all of them, write a brief plain-text summary listing "
        "which tools you used and STOP immediately. Do NOT call any more tools, do not "
        "repeat any step, and do not modify or create any files other than the ones "
        "described. Your final message must be plain text with no tool calls."
    )


async def phase_exercise(
    ws,
    rpc: RpcClient,
    session_id: str,
    base_seq: int,
    pty,
    port: int,
    turn_timeout: int,
) -> tuple[int, int]:
    total = len(EXERCISE_TURNS)
    all_tools: set[str] = set()
    all_results: dict[str, dict] = {}
    turn_failures = 0
    for part in range(1, total + 1):
        name = EXERCISE_TURNS[part - 1]["name"]
        marker = EXERCISE_TURNS[part - 1]["marker"]
        prompt = build_exercise_turn_prompt(part, total, port)
        status, summary, seen_seq = await _run_turn(
            name, ws, rpc, session_id, base_seq, prompt, marker, pty, turn_timeout
        )
        base_seq = seen_seq
        all_tools.update(summary["tools"] or [])
        all_results.update(_tool_result_map(summary))
        if status == "timeout":
            turn_failures += 1
        await _finish_turn(status, pty)
        await asyncio.sleep(TURN_GAP_S)

    tools = all_tools
    results = all_results

    checks: list[tuple[str, bool]] = []
    missing = sorted(REQUIRED_TOOLS - tools)
    checks.append(("all required tools invoked", not missing))
    for tool in REQUIRED_TOOLS:
        if tool in tools:
            tr = results.get(tool, {})
            ok = tr.get("success") is True if tr else True
            checks.append((f"{tool} succeeded", ok))

    lsp_notes: list[str] = []
    for tool in LSP_TOOLS:
        invoked = tool in tools
        checks.append((f"{tool} invoked", invoked))
        tr = results.get(tool)
        if tr:
            ok = tr.get("success") is True
            lsp_notes.append(f"{tool}: {'ok' if ok else 'failed'} - {tr.get('error', '')[:80]}")

    for rel, expected, what in ARTIFACT_EXPECTATIONS:
        actual = _read_stripped(rel)
        checks.append((f"{rel} content matches ({what})", actual == expected))

    checks.append(("temp_delete.txt was deleted", not (TURN2_DIR / DELETED_ARTIFACT).exists()))

    optional = {rel: _read_stripped(rel) for rel in OPTIONAL_ARTIFACTS}
    detail_parts = [
        f"turns_with_timeout={turn_failures}",
        f"missing_tools={missing or 'none'}",
        f"fetched.txt={'written' if optional['fetched.txt'] else 'MISSING'}",
        f"lsp_result.txt={'written' if optional['lsp_result.txt'] else 'MISSING'}",
    ]
    if lsp_notes:
        detail_parts.append("lsp=" + " | ".join(lsp_notes))
    failures = _report("2. MULTI-TOOL EXERCISE", checks, " ; ".join(detail_parts))
    return failures, base_seq


# ── Main ──────────────────────────────────────────────────────────────────────


async def main() -> int:
    global _pty_log
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="All-tools smoke test (visible winpty console).")
    parser.add_argument(
        "--turn-timeout", type=int, default=int(os.environ.get("SMOKE_TURN_TIMEOUT", "600"))
    )
    args = parser.parse_args()

    _prepare_artifacts()

    port = get_free_port()
    child_env = dict(os.environ)
    child_env["ZENITH_BACKEND_URL"] = f"http://127.0.0.1:{port}"
    child_env["TERM"] = "xterm-256color"
    child_env.pop("CI", None)
    child_env.pop("NO_COLOR", None)
    child_env.pop("FORCE_COLOR", None)

    backend = None
    pty = None
    try:
        print(f"[tools] backend -> http://127.0.0.1:{port}  (own console window)")
        backend = spawn_backend(port, child_env)
        ok, last = wait_health(port, int(os.environ.get("SMOKE_BACKEND_WAIT", "90")))
        if not ok:
            print(f"[tools] FAIL backend never became healthy. Last health result: {last}")
            return 1
        print(f"[tools] backend healthy: {last}")

        _pty_log = PtyLog()
        tui_argv = _resolve_tui_argv()
        print(f"[tools] spawning TUI (visible winpty console): {tui_argv}")
        console_before = _enum_console_windows()
        backend_kind = getattr(Backend, "WinPTY", 1) if Backend is not None else 1
        pty = PtyProcess.spawn(
            tui_argv,
            cwd=str(ROOT),
            env=child_env,
            dimensions=(40, 160),
            backend=backend_kind,
        )
        print(f"[tools] TUI pid={pty.pid}")
        show_tui_window(console_before)
        threading.Thread(target=pty_reader, args=(pty, _pty_log), daemon=True).start()
        await _wait_tui_ready(_pty_log)
        print("[tools] TUI main input visible")

        async with ws_connect(
            f"ws://127.0.0.1:{port}/ws",
            ping_interval=None,
            open_timeout=10,
            max_size=8 * 1024 * 1024,
        ) as ws:
            rpc = RpcClient(ws)
            baseline = ""
            try:
                for s in await rpc.call("session.list") or []:
                    baseline = max(baseline, s.get("created_at", ""))
            except Exception:
                baseline = ""
            print(f"[tools] session baseline: {baseline or '(no prior sessions)'}")

            await type_text(pty, "Hello", 0.02)
            session = await wait_for_session(
                rpc, baseline, int(os.environ.get("SMOKE_SESSION_WAIT", "60"))
            )
            session_id = session["id"]
            print(f"[tools] session created: {session_id} ({session.get('title')!r})")

            print(
                "[tools] waiting for the greeting turn to finish (clean composer before phase 1) ..."
            )
            try:
                gstatus, _gevents, _gterminal, base_seq = await wait_for_turn_end(
                    rpc, session_id, 0, pty, args.turn_timeout
                )
            except TimeoutError as exc:
                print(f"[tools] FAIL greeting turn did not complete: {exc}")
                return 1
            if gstatus != "success":
                print(f"[tools] FAIL greeting turn ended with status={gstatus}")
                _log_tui_tail(_pty_log, name="on greeting failure")
                return 1
            print(f"[tools] greeting turn complete (status={gstatus}, next seq={base_seq})")
            await _wait_idle(_pty_log)

            total_failures = 0
            failures, base_seq = await phase_inventory(
                ws, rpc, session_id, base_seq, pty, args.turn_timeout
            )
            total_failures += failures
            await asyncio.sleep(TURN_GAP_S)

            failures, base_seq = await phase_exercise(
                ws, rpc, session_id, base_seq, pty, port, args.turn_timeout
            )
            total_failures += failures

            print()
            print("=" * 72)
            print("ALL-TOOLS SMOKE TEST REPORT")
            print("=" * 72)
            print(f"backend   : http://127.0.0.1:{port}  pid={backend.pid}")
            print(f"tui pid   : {pty.pid}")
            print(f"session   : {session_id}")
            print(f"artifacts : {ARTIFACTS_ROOT.relative_to(ROOT)} (kept for inspection)")
            print("expected tools: " + ", ".join(sorted(REQUIRED_TOOLS | LSP_TOOLS)))
            if total_failures:
                print(f"\nRESULT: FAIL ({total_failures} failed checks)")
            else:
                print("\nRESULT: PASS")
            return 1 if total_failures else 0

    except TimeoutError as exc:
        print(f"[tools] FAIL: {exc}")
        if _pty_log is not None:
            _log_tui_tail(_pty_log, name="on timeout")
        return 1
    except Exception as exc:
        print(f"[tools] FAIL: {type(exc).__name__}: {exc}")
        if _pty_log is not None:
            _log_tui_tail(_pty_log, name="on error")
        return 1
    finally:
        _cleanup(backend, pty, ARTIFACTS_ROOT, keep_probe=True)


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
