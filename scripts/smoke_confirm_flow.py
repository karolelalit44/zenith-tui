"""Auto-approval flow smoke test.

Boots the real backend and the real TUI in a visible winpty console (the same
environment as ``smoke_tui_session.py`` / smoke run5) and walks a single probe
file through the full create/update/delete lifecycle:

1. create (new file)   - no confirmation, file written with the exact defined
   content at a defined location
2. update (existing file) - auto_overwrite=true, overwrite passes straight
   through and the content is updated correctly
3. delete (risky op)   - auto_risky=true, deletion passes straight through and
   the file is removed

For each case it verifies explicitly:

  * the expected tool (file_write / file_delete) is the one that gets called
  * no confirmation request is ever raised (interactive confirmations removed)
  * the tool side-effect matches the auto-approval decision (file created /
    updated / deleted)
  * the model proceeds to the next step afterwards (the turn completes with a
    final message instead of hanging)

The config flags ``auto_overwrite`` and ``auto_risky`` both default to ``true``,
so the whole lifecycle runs without any user round-trip.

Usage::

    .venv\\Scripts\\python.exe scripts/smoke_confirm_flow.py [--turn-timeout 240]

Env overrides (optional, same as smoke_tui_session.py):
    SMOKE_BACKEND_WAIT / SMOKE_TUI_READY_WAIT / SMOKE_SESSION_WAIT
    SMOKE_TURN_TIMEOUT / SMOKE_TYPE_DELAY_MS / SMOKE_TURN_GAP_S
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from smoke_tui_session import (
    ERROR_GRACE_S,
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
    type_text,
    wait_for_session,
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

_pty_log: PtyLog | None = None


def _probe_files(stamp: str) -> tuple[Path, str]:
    path = ROOT / f"scripts/confirm_probe_{stamp}.txt"
    return path, f"scripts/confirm_probe_{stamp}.txt"


def summarize(events: list[dict]) -> dict:
    tools: list[str] = []
    tool_results: list[dict] = []
    warnings: list[str] = []
    message = ""
    iterations = 0
    error_code = ""
    for e in events:
        kind = e.get("event_type") or e.get("kind", "")
        data = e.get("event_data") or {}
        if kind == "tool_call":
            t = data.get("tool", "?")
            if t not in tools:
                tools.append(t)
        elif kind == "tool_result":
            tool_results.append(
                {
                    "tool": data.get("tool", "?"),
                    "success": data.get("success"),
                    "error": str(data.get("error", ""))[:160],
                }
            )
        elif kind == "warning":
            warnings.append(f"{data.get('code', '?')}: {str(data.get('message', ''))[:150]}")
        elif kind == "success":
            iterations = int(data.get("iterations", 0))
            if not message:
                message = str(data.get("message", ""))
        elif kind == "error":
            error_code = str(data.get("code", ""))
        elif kind == "message":
            text = str(data.get("text", "")).strip()
            if text and not message:
                message = text[:300]
    return {
        "tools": tools,
        "tool_results": tool_results,
        "warnings": warnings,
        "message": message,
        "iterations": iterations,
        "error_code": error_code,
    }


async def wait_turn_end(
    ws,
    rpc: RpcClient,
    session_id: str,
    base_seq: int,
    timeout: int,
) -> tuple[str, list[dict], int]:
    """Poll session.sync until the turn ends."""
    seen_seq = base_seq
    events: list[dict] = []
    candidate: dict | None = None
    last_activity = time.monotonic()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        res = await rpc.call(
            "session.sync", {"session_id": session_id, "since_sequence": seen_seq}, timeout=30
        )
        batch = res.get("events", []) or []
        if batch:
            seen_seq = max(seen_seq, max(e.get("sequence", 0) for e in batch))
        for e in batch:
            kind = e.get("event_type") or e.get("kind", "")
            data = e.get("event_data") or {}
            events.append(e)
            last_activity = time.monotonic()
            if kind == "success" and isinstance(data.get("iterations"), (int, float)):
                return "success", events, seen_seq
            if kind == "error":
                if not data.get("recoverable"):
                    return "error", events, seen_seq
                candidate = e
        if candidate is not None and time.monotonic() - last_activity >= ERROR_GRACE_S:
            return "error", events, seen_seq
        await asyncio.sleep(1)
    raise TimeoutError(f"Turn did not complete within {timeout}s (session={session_id})")


def _check(checks: list[tuple[str, bool]], details: str) -> int:
    failures = 0
    for label, ok in checks:
        print(f"    [{PASS if ok else FAIL}] {label}")
        if not ok:
            failures += 1
    if details:
        print(f"    detail: {details}")
    return failures


INITIAL_CONTENT = "line one\nline two"
UPDATED_CONTENT = "line one\nzenith smoke ok"


async def _run_turn(
    name: str,
    ws,
    rpc: RpcClient,
    session_id: str,
    base_seq: int,
    prompt: str,
    pty,
    turn_timeout: int,
) -> tuple[str, dict, int]:
    """Send ``prompt``, wait for the turn to end, and summarize the result."""
    print(f"\n[flow] === scenario: {name} ===")
    if not await _wait_idle(_pty_log):
        raise RuntimeError(
            f"{name}: composer not idle before typing; refusing to type into a disabled composer"
        )
    print(f"[flow] typing: {prompt}")
    await type_text(pty, prompt, 0.02)

    try:
        status, events, seen_seq = await wait_turn_end(ws, rpc, session_id, base_seq, turn_timeout)
    except TimeoutError as exc:
        print(f"[flow]   {name}: TIMEOUT ({exc})")
        _log_tui_tail(_pty_log, name=f"on {name} timeout")
        return "timeout", {}, base_seq

    summary = summarize(events)
    print(f"[flow]   status={status} iterations={summary['iterations']}")
    print(f"[flow]   tools={summary['tools'] or 'none'}")
    for w in summary["warnings"]:
        print(f"[flow]   warning: {w}")
    print(f"[flow]   final message: {summary['message'] or '(empty)'}")
    return status, summary, seen_seq


async def _wait_idle(log: PtyLog, timeout: int = 25) -> bool:
    """Wait until the composer is enabled and no banner/Working frame remains."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _composer_idle(log):
            return True
        await asyncio.sleep(0.5)
    return False


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


async def _dismiss_retry_banner(log: PtyLog, pty) -> None:
    """Dismiss the TUI retry banner with Esc, only once it has rendered.

    Detection reads the recent pty tail (never the whole history, which keeps
    old banners) and keys off the disabled-composer hint, so Esc cannot fire
    early and abort a still-running turn (App.tsx escapes -> abort).
    """
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


def _report(name: str, checks: list[tuple[str, bool]], detail: str) -> int:
    print(f"\n[flow] --- {name} ---")
    return _check(checks, detail)


async def phase_create(
    ws,
    rpc: RpcClient,
    session_id: str,
    base_seq: int,
    probe_rel: str,
    probe_path: Path,
    pty,
    turn_timeout: int,
) -> tuple[int, int]:
    prompt = (
        f"Create a new file at {probe_rel} whose exact content is the two lines "
        f"'line one' and 'line two' separated by a newline, with no trailing newline "
        f"at the end. Use the file_write tool exactly once. Do not read, verify, or "
        f"rewrite the file, and do not use any other tools. Report the result and stop."
    )
    status, summary, seen_seq = await _run_turn(
        "1. create (new file) - auto-approved, no confirmation",
        ws,
        rpc,
        session_id,
        base_seq,
        prompt,
        pty,
        turn_timeout,
    )
    content = probe_path.read_text(encoding="utf-8") if probe_path.exists() else None
    checks = [
        ("tool attempted: file_write", "file_write" in summary["tools"]),
        (
            "file_write success",
            any(
                tr["tool"] == "file_write" and tr["success"] is True
                for tr in summary["tool_results"]
            ),
        ),
        ("file content matches the defined content", content == INITIAL_CONTENT),
        ("turn completed cleanly (no timeout)", status != "timeout"),
        ("model proceeded (final message present)", bool(summary["message"].strip())),
    ]
    note = []
    if status not in ("success", "timeout") and summary.get("error_code"):
        note.append(f"turn ended with recoverable error code={summary['error_code']}")
    detail = f"file_after={content!r} final_message={summary['message'][:120]!r}" + (
        f" ; note: {'; '.join(note)}" if note else ""
    )
    failures = _report("1. CREATE", checks, detail)
    await _finish_turn(status, pty)
    return failures, seen_seq


async def phase_update(
    ws,
    rpc: RpcClient,
    session_id: str,
    base_seq: int,
    probe_rel: str,
    probe_path: Path,
    pty,
    turn_timeout: int,
) -> tuple[int, int]:
    prompt = (
        f"The file {probe_rel} already exists on disk. Update it: change its second "
        f"line to exactly 'zenith smoke ok', keeping the first line 'line one' "
        f"unchanged. Use the file_write tool exactly once - after the write succeeds, "
        f"do NOT call any more tools; report the outcome and stop. Do not use any "
        f"other tools."
    )
    status, summary, seen_seq = await _run_turn(
        "2. update (existing file) - auto_overwrite=true, no confirmation",
        ws,
        rpc,
        session_id,
        base_seq,
        prompt,
        pty,
        turn_timeout,
    )
    content = probe_path.read_text(encoding="utf-8") if probe_path.exists() else None
    checks = [
        ("tool attempted: file_write", "file_write" in summary["tools"]),
        (
            "file_write success (overwrite allowed automatically)",
            any(
                tr["tool"] == "file_write" and tr["success"] is True
                for tr in summary["tool_results"]
            ),
        ),
        ("file content updated correctly", content == UPDATED_CONTENT),
        ("turn completed cleanly (no timeout)", status != "timeout"),
        ("model proceeded (final message present)", bool(summary["message"].strip())),
    ]
    note = []
    if status not in ("success", "timeout") and summary.get("error_code"):
        note.append(f"turn ended with recoverable error code={summary['error_code']}")
    detail = f"file_after={content!r} final_message={summary['message'][:120]!r}" + (
        f" ; note: {'; '.join(note)}" if note else ""
    )
    failures = _report("2. UPDATE", checks, detail)
    await _finish_turn(status, pty)
    return failures, seen_seq


async def phase_delete(
    ws,
    rpc: RpcClient,
    session_id: str,
    base_seq: int,
    probe_rel: str,
    probe_path: Path,
    pty,
    turn_timeout: int,
) -> tuple[int, int]:
    prompt = (
        f"The file {probe_rel} already exists on disk with the two lines "
        f"'line one' and 'zenith smoke ok'. Delete this file using the file_delete "
        f"tool exactly once. Do NOT write to, create, or update the file - the only "
        f"tool call you are allowed to make is file_delete. Then report the deletion "
        f"and stop."
    )
    status, summary, seen_seq = await _run_turn(
        "3. delete (risky op) - auto_risky=true, no confirmation",
        ws,
        rpc,
        session_id,
        base_seq,
        prompt,
        pty,
        turn_timeout,
    )
    deleted = not probe_path.exists()
    checks = [
        ("tool attempted: file_delete", "file_delete" in summary["tools"]),
        (
            "file_delete success (risky op allowed automatically)",
            any(
                tr["tool"] == "file_delete" and tr["success"] is True
                for tr in summary["tool_results"]
            ),
        ),
        ("file no longer exists", deleted),
        ("turn completed cleanly (no timeout)", status != "timeout"),
        ("model proceeded (final message present)", bool(summary["message"].strip())),
    ]
    note = []
    if status not in ("success", "timeout") and summary.get("error_code"):
        note.append(f"turn ended with recoverable error code={summary['error_code']}")
    detail = f"file_deleted={deleted} final_message={summary['message'][:120]!r}" + (
        f" ; note: {'; '.join(note)}" if note else ""
    )
    failures = _report("3. DELETE", checks, detail)
    await _finish_turn(status, pty)
    return failures, seen_seq


async def main() -> int:
    global _pty_log
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Auto-approval flow smoke test.")
    parser.add_argument(
        "--turn-timeout", type=int, default=int(os.environ.get("SMOKE_TURN_TIMEOUT", "240"))
    )
    args = parser.parse_args()

    stamp = time.strftime("%Y%m%d_%H%M%S")
    probe_path, probe_rel = _probe_files(stamp)

    for stale in sorted(ROOT.glob("scripts/confirm_probe_*.txt")):
        try:
            stale.unlink()
        except OSError:
            pass

    port = get_free_port()
    child_env = dict(os.environ)
    child_env["ZENITH_BACKEND_URL"] = f"http://127.0.0.1:{port}"
    child_env["TERM"] = "xterm-256color"
    child_env.pop("CI", None)
    child_env.pop("NO_COLOR", None)
    child_env.pop("FORCE_COLOR", None)

    backend = None
    pty = None
    exit_code = 1
    try:
        print(f"[flow] backend    -> http://127.0.0.1:{port}  (own console window)")
        print(f"[flow] probe file -> {probe_rel}")
        backend = spawn_backend(port, child_env)
        ok, last = wait_health(port, int(os.environ.get("SMOKE_BACKEND_WAIT", "90")))
        if not ok:
            print(f"[flow] FAIL backend never became healthy. Last health result: {last}")
            return 1
        print(f"[flow] backend healthy: {last}")

        _pty_log = PtyLog()
        tui_argv = _resolve_tui_argv()
        print(f"[flow] spawning TUI (visible winpty console): {tui_argv}")
        console_before = _enum_console_windows()
        backend_kind = getattr(Backend, "WinPTY", 1) if Backend is not None else 1
        pty = PtyProcess.spawn(
            tui_argv,
            cwd=str(ROOT),
            env=child_env,
            dimensions=(40, 160),
            backend=backend_kind,
        )
        print(f"[flow] TUI pid={pty.pid}")
        show_tui_window(console_before)

        threading.Thread(target=pty_reader, args=(pty, _pty_log), daemon=True).start()

        await _wait_tui_ready(_pty_log)
        print("[flow] TUI main input visible")

        async with ws_connect(
            f"ws://127.0.0.1:{port}/ws",
            ping_interval=None,
            open_timeout=10,
            max_size=4 * 1024 * 1024,
        ) as ws:
            rpc = RpcClient(ws)
            baseline = ""
            try:
                for s in await rpc.call("session.list") or []:
                    baseline = max(baseline, s.get("created_at", ""))
            except Exception:
                baseline = ""
            print(f"[flow] session baseline: {baseline or '(no prior sessions)'}")

            await type_text(pty, "Hello", 0.02)
            session = await wait_for_session(
                rpc, baseline, int(os.environ.get("SMOKE_SESSION_WAIT", "60"))
            )
            session_id = session["id"]
            print(f"[flow] session created: {session_id} ({session.get('title')!r})")
            base_seq = 0

            print("[flow] warm-up turn (greeting) ...")
            status, events, seen_seq = await wait_turn_end(ws, rpc, session_id, base_seq, 240)
            base_seq = seen_seq
            print(f"[flow] warm-up status={status} events={len(events)}")
            if status != "success":
                await _dismiss_retry_banner(_pty_log, pty)
            await asyncio.sleep(2.0)

            total_failures = 0

            failures, base_seq = await phase_create(
                ws, rpc, session_id, base_seq, probe_rel, probe_path, pty, args.turn_timeout
            )
            total_failures += failures

            failures, base_seq = await phase_update(
                ws, rpc, session_id, base_seq, probe_rel, probe_path, pty, args.turn_timeout
            )
            total_failures += failures

            failures, base_seq = await phase_delete(
                ws, rpc, session_id, base_seq, probe_rel, probe_path, pty, args.turn_timeout
            )
            total_failures += failures

            print()
            print("=" * 72)
            print("AUTO-APPROVAL FLOW REPORT")
            print("=" * 72)
            print(f"backend   : http://127.0.0.1:{port}  pid={backend.pid}")
            print(f"tui pid   : {pty.pid}")
            print(f"session   : {session_id}")
            print(
                "scenarios : 1. create / 2. update (auto_overwrite=true) / 3. delete (auto_risky=true)"
            )
            print(
                "flags     : auto_overwrite=true auto_risky=true (defaults) - no confirmation raised"
            )
            if total_failures:
                print(f"\nRESULT: FAIL ({total_failures} failed checks)")
            else:
                print("\nRESULT: PASS")
            exit_code = 1 if total_failures else 0
            return exit_code

    except TimeoutError as exc:
        print(f"[flow] FAIL: {exc}")
        if _pty_log is not None:
            _log_tui_tail(_pty_log, name="on timeout")
        return 1
    except Exception as exc:
        print(f"[flow] FAIL: {type(exc).__name__}: {exc}")
        if _pty_log is not None:
            _log_tui_tail(_pty_log, name="on error")
        return 1
    finally:
        _cleanup(backend, pty, probe_path, keep_probe=True)


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
