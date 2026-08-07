"""Smoke-test driver for the Zenith backend + Ink TUI.

Boots the real backend and the real TUI in *visible* console windows
(winpty backend, not headless), types real prompts into the TUI, and
verifies behavior by polling the backend's ``session.sync`` JSON-RPC
endpoint over a driver-owned WebSocket.

Turns: greeting -> topic -> implementation. Asserts:
  * greeting/topic produce zero tool calls
  * implementation produces at least one of file_write/file_edit/bash
  * the requested probe file is created with the expected content
Reports per-turn tool names, event kinds, token info, and confirmations.

Usage::

    .venv\\Scripts\\python.exe scripts/smoke_tui_session.py

Env overrides (all optional):
    SMOKE_BACKEND_WAIT    seconds to wait for /health        (default 90)
    SMOKE_TUI_READY_WAIT  seconds to wait for TUI main input  (default 90)
    SMOKE_SESSION_WAIT    seconds to wait for session.create  (default 60)
    SMOKE_TURN_TIMEOUT    seconds per turn                    (default 360)
    SMOKE_TYPE_DELAY_MS   pause after typing the prompt       (default 20)
    SMOKE_TURN_GAP_S      pause between turns                 (default 2.0)
    SMOKE_ERROR_GRACE_S   how long a recoverable error must be
                          silent before it counts as turn end  (default 15.0)
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

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
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
TSX_CLI = ROOT / "node_modules" / "tsx" / "dist" / "cli.mjs"

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][0-9A-Z]|\x1b[=>]|\x1b\][^\x07]*(?:\x07|\x1b\\)")

BACKEND_WAIT = int(os.environ.get("SMOKE_BACKEND_WAIT", "90"))
TUI_READY_WAIT = int(os.environ.get("SMOKE_TUI_READY_WAIT", "90"))
SESSION_WAIT = int(os.environ.get("SMOKE_SESSION_WAIT", "60"))
TURN_TIMEOUT = int(os.environ.get("SMOKE_TURN_TIMEOUT", "360"))
TYPE_DELAY_MS = int(os.environ.get("SMOKE_TYPE_DELAY_MS", "20"))
TURN_GAP_S = float(os.environ.get("SMOKE_TURN_GAP_S", "2.0"))
ERROR_GRACE_S = float(os.environ.get("SMOKE_ERROR_GRACE_S", "15.0"))

TUI_READY_MARKERS = ("Ask anything", "Describe the change", "? help")

SCHEMA_BUDGET = {"build": 628, "plan": 476, "registry": 1407}


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text).replace("\x1b", "")


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def spawn_backend(port: int, env: dict) -> subprocess.Popen:
    args = [
        str(PYTHON),
        "-m",
        "server.main",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    log_path = ROOT / "scripts" / "_diag_backend.log"
    logf = open(log_path, "w", encoding="utf-8", errors="replace")  # noqa: SIM115 (kept open for Popen lifetime)
    return subprocess.Popen(
        args,
        cwd=str(ROOT),
        env=env,
        stdout=logf,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


CONSOLE_CLASSES = ("ConsoleWindowClass", "PseudoConsoleWindow")


def _enum_console_windows() -> set[int]:
    try:
        user32 = ctypes.windll.user32
    except Exception:
        return set()

    found: set[int] = set()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(hwnd, _lparam):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value in CONSOLE_CLASSES:
            found.add(hwnd)
        return True

    user32.EnumWindows(_cb, 0)
    return found


def show_tui_window(before: set[int], timeout: float = 15.0) -> None:
    """The winpty/conpty console window is created hidden; force it visible.

    ``before`` is the set of console-window HWNDs enumerated just before the
    TUI was spawned; any new ``ConsoleWindowClass``/``PseudoConsoleWindow``
    window belongs to the TUI's console and gets shown and raised.
    """
    try:
        user32 = ctypes.windll.user32
    except Exception:
        return
    SW_SHOW = 5
    SW_RESTORE = 9
    HWND_TOP = 0
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_SHOWWINDOW = 0x0040
    deadline = time.monotonic() + timeout
    shown = False
    while time.monotonic() < deadline:
        for hwnd in _enum_console_windows() - before:
            try:
                user32.ShowWindow(hwnd, SW_SHOW)
                user32.ShowWindow(hwnd, SW_RESTORE)
                user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                user32.SetForegroundWindow(hwnd)
                shown = True
            except Exception:
                pass
        if shown:
            break
        time.sleep(0.25)
    if shown:
        print("[smoke] TUI console window shown")
    else:
        print("[smoke] note: could not find the TUI console window to show")


def wait_health(port: int, timeout: int) -> tuple[bool, str]:
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                body = json.loads(r.read().decode())
                if body.get("status") == "ok" and body.get("handler"):
                    return True, json.dumps(body)
                last = json.dumps(body)
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(1)
    return False, last


class PtyLog:
    def __init__(self) -> None:
        self._buf: list[str] = []
        self._lock = threading.Lock()
        self._max = 300_000

    def append(self, chunk: str) -> None:
        with self._lock:
            self._buf.append(chunk)
            if len("".join(self._buf)) > self._max:
                joined = "".join(self._buf)
                self._buf = [joined[-self._max:]]

    def text(self) -> str:
        with self._lock:
            return "".join(self._buf)

    def find(self, marker: str) -> bool:
        return marker in self.text()


def pty_reader(proc: PtyProcess, log: PtyLog) -> None:
    while True:
        try:
            chunk = proc.read(4096)
        except EOFError:
            break
        except Exception:
            break
        if chunk:
            log.append(chunk)


class RpcClient:
    def __init__(self, ws) -> None:
        self._ws = ws
        self._counter = 0

    async def call(self, method: str, params: dict | None = None, timeout: float = 30.0):
        self._counter += 1
        rid = f"smoke_{self._counter}"
        payload = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            payload["params"] = params
        await self._ws.send(json.dumps(payload))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=max(0.1, deadline - time.monotonic()))
            data = json.loads(raw)
            if data.get("id") == rid:
                if data.get("error"):
                    raise RuntimeError(f"RPC {method} error: {data['error']['message']}")
                return data.get("result")
        raise TimeoutError(f"RPC timeout: {method}")


async def wait_for_session(rpc: RpcClient, baseline: str, timeout: int) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sessions = await rpc.call("session.list") or []
        ours = [s for s in sessions if s.get("created_at", "") > baseline]
        if ours:
            return max(ours, key=lambda s: s["created_at"])
        await asyncio.sleep(1)
    raise TimeoutError(f"No session created after baseline {baseline!r}")


async def wait_for_turn_end(
    rpc: RpcClient,
    session_id: str,
    base_seq: int,
    pty: PtyProcess | None,
    timeout: int,
    on_confirmation,
) -> tuple[str, list[dict], dict, int]:
    seen_seq = base_seq
    collected: list[dict] = []
    confirmed: set[str] = set()
    candidate: dict | None = None
    last_activity: float = time.monotonic()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        res = await rpc.call(
            "session.sync",
            {"session_id": session_id, "since_sequence": seen_seq},
            timeout=30,
        )
        events = res.get("events", []) or []
        if events:
            seen_seq = max(seen_seq, max(e.get("sequence", 0) for e in events))
        for e in events:
            kind = e.get("event_type") or e.get("kind", "")
            data = e.get("event_data") or {}
            collected.append(e)
            last_activity = time.monotonic()
            if kind == "success" and isinstance(data.get("iterations"), (int, float)):
                return "success", collected, e, seen_seq
            if kind == "error":
                if not data.get("recoverable"):
                    return "error", collected, e, seen_seq
                candidate = e
            if kind == "confirmation_request":
                cid = data.get("confirmation_id")
                if cid and cid not in confirmed:
                    confirmed.add(cid)
                    await on_confirmation(cid)
        if candidate is not None and time.monotonic() - last_activity >= ERROR_GRACE_S:
            return "error", collected, candidate, seen_seq
        await asyncio.sleep(1)
    raise TimeoutError(f"Turn did not complete within {timeout}s (session={session_id})")


def summarize_turn(events: list[dict]) -> dict:
    kinds: list[str] = []
    tools: list[str] = []
    tool_results: dict[str, dict] = {}
    confirmations: list[str] = []
    tokens: dict | None = None
    iterations: int = 0
    message = ""
    warnings: list[str] = []
    for e in events:
        kind = e.get("event_type") or e.get("kind", "")
        data = e.get("event_data") or {}
        kinds.append(kind)
        if kind == "tool_call":
            t = data.get("tool", "?")
            if t not in tools:
                tools.append(t)
        elif kind == "tool_result":
            t = data.get("tool", "?")
            tool_results[t] = {
                "success": data.get("success"),
                "error": str(data.get("error", ""))[:120],
                "output_len": len(str(data.get("output", ""))),
            }
        elif kind == "confirmation_request":
            confirmations.append(str(data.get("confirmation_id", "?")))
        elif kind == "success":
            iterations = int(data.get("iterations", 0))
            tokens = data.get("tokenInfo")
            message = str(data.get("message", ""))
        elif kind == "warning":
            warnings.append(f"{data.get('code', '?')}: {str(data.get('message', ''))[:120]}")
    return {
        "kinds": kinds,
        "tools": tools,
        "tool_results": tool_results,
        "confirmations": confirmations,
        "tokens": tokens,
        "iterations": iterations,
        "message": message,
        "warnings": warnings,
    }


def fmt_tokens(tokens: dict | None) -> str:
    if not tokens:
        return "n/a"
    parts = [
        f"used={tokens.get('used')}",
        f"remaining={tokens.get('remaining')}",
        f"total={tokens.get('total')}",
        f"percent={tokens.get('percent')}%",
        f"prompt={tokens.get('prompt_tokens')}",
        f"completion={tokens.get('completion_tokens')}",
        f"cached={tokens.get('cached_tokens')}",
        f"est={tokens.get('estimated')}",
        f"mode={tokens.get('mode')}",
    ]
    return " ".join(parts)


async def type_text(proc: PtyProcess, text: str, delay_s: float) -> None:
    proc.write(text)
    await asyncio.sleep(max(delay_s, 0.2))
    proc.write("\r")


async def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Smoke-test the Zenith TUI (visible winpty console).")
    parser.add_argument("--type-delay-ms", type=int, default=TYPE_DELAY_MS, help="pause (ms) after typing the prompt")
    parser.add_argument("--turn-timeout", type=int, default=TURN_TIMEOUT)
    parser.add_argument("--keep-probe", action="store_true", help="Do not delete the probe file on success")
    args = parser.parse_args()

    stamp = time.strftime("%Y%m%d_%H%M%S")
    probe_rel = f"scripts/smoke_probe_{stamp}.txt"
    probe_path = ROOT / probe_rel

    port = get_free_port()
    child_env = dict(os.environ)
    child_env["ZENITH_BACKEND_URL"] = f"http://127.0.0.1:{port}"
    child_env["TERM"] = "xterm-256color"
    child_env.pop("CI", None)
    child_env.pop("NO_COLOR", None)
    child_env.pop("FORCE_COLOR", None)

    backend = None
    pty: PtyProcess | None = None
    log: PtyLog | None = None
    exit_code = 1

    turns = [
        {
            "name": "greeting",
            "prompt": "Hello! Say hi and introduce yourself in a sentence or two. No tools needed.",
            "expect": "none",
        },
        {
            "name": "topic",
            "prompt": (
                "What tools do you have available? Summarize the toolkit and roughly how many "
                "schema tokens the build-mode and plan-mode tool registries use. No tools needed."
            ),
            "expect": "none",
        },
        {
            "name": "implementation",
            "prompt": (
                f"Create a file named {probe_rel} in this repository. "
                "Its content must be exactly: zenith smoke ok"
            ),
            "expect": "write",
        },
    ]

    try:
        print(f"[smoke] backend    -> http://127.0.0.1:{port}  (own console window)")
        print(f"[smoke] probe file -> {probe_rel}")
        backend = spawn_backend(port, child_env)
        ok, last = wait_health(port, BACKEND_WAIT)
        if not ok:
            print(f"[smoke] FAIL backend never became healthy. Last health result: {last}")
            return 1
        print(f"[smoke] backend healthy: {last}")

        log = PtyLog()
        tui_argv = _resolve_tui_argv()
        print(f"[smoke] spawning TUI (visible winpty console): {tui_argv}")
        console_before = _enum_console_windows()
        backend_kind = getattr(Backend, "WinPTY", 1) if Backend is not None else 1
        pty = PtyProcess.spawn(
            tui_argv,
            cwd=str(ROOT),
            env=child_env,
            dimensions=(40, 160),
            backend=backend_kind,
        )
        print(f"[smoke] TUI pid={pty.pid}")
        show_tui_window(console_before)

        threading.Thread(target=pty_reader, args=(pty, log), daemon=True).start()

        await _wait_tui_ready(log)
        print("[smoke] TUI main input visible")

        async with ws_connect(
            f"ws://127.0.0.1:{port}/ws", ping_interval=None, open_timeout=10, max_size=4 * 1024 * 1024
        ) as ws:
            rpc = RpcClient(ws)
            baseline = ""
            try:
                for s in await rpc.call("session.list") or []:
                    baseline = max(baseline, s.get("created_at", ""))
            except Exception:
                baseline = ""
            print(f"[smoke] session baseline: {baseline or '(no prior sessions)'}")

            results = []
            session_id: str | None = None
            base_seq = 0

            async def approve_confirmation(cid: str) -> None:
                print(f"[smoke]   confirmation approved: {cid}")
                try:
                    await rpc.call(
                        "confirmation.response", {"confirmation_id": cid, "approved": True}, timeout=10
                    )
                except Exception as exc:
                    print(f"[smoke]   RPC approve failed ({exc}); relying on TUI 'y'")
                if pty and pty.isalive():
                    pty.write("y")

            for turn in turns:
                print(f"\n[smoke] === turn: {turn['name']} ===")
                print(f"[smoke] typing: {turn['prompt']}")
                await type_text(pty, turn["prompt"], args.type_delay_ms / 1000.0)

                if session_id is None:
                    session = await wait_for_session(rpc, baseline, SESSION_WAIT)
                    session_id = session["id"]
                    print(f"[smoke] session created: {session['id']} ({session.get('title')!r})")

                print(f"[smoke] waiting for turn completion (timeout {args.turn_timeout}s) ...")
                status, events, _terminal, base_seq = await wait_for_turn_end(
                    rpc, session_id, base_seq, pty, args.turn_timeout, approve_confirmation
                )
                summary = summarize_turn(events)
                results.append((turn, status, summary))
                print(f"[smoke]   status={status} iterations={summary['iterations']}")
                print(f"[smoke]   tools={summary['tools'] or 'none'}")
                print(f"[smoke]   kinds={summary['kinds']}")
                if summary["confirmations"]:
                    print(f"[smoke]   confirmations={summary['confirmations']}")
                for w in summary["warnings"]:
                    print(f"[smoke]   warning: {w}")
                print(f"[smoke]   tokens: {fmt_tokens(summary['tokens'])}")
                if status != "success":
                    print(f"[smoke]   terminal message: {summary['message']}")
                _log_tui_tail(log, name=f"after {turn['name']}")
                await asyncio.sleep(TURN_GAP_S)

            failed: list[str] = []
            for turn, status, summary in results:
                name = turn["name"]
                tools = summary["tools"]
                if status != "success":
                    failed.append(f"{name}: terminal status was {status}")
                if turn["expect"] == "none" and tools:
                    failed.append(f"{name}: expected zero tool calls, got {tools}")
                if turn["expect"] == "write" and not any(
                    t in tools for t in ("file_write", "file_edit", "bash")
                ):
                    failed.append(
                        f"{name}: expected file_write/file_edit/bash, got {tools or 'none'}"
                    )

            probe_ok = False
            probe_found = probe_path.exists()
            if probe_found:
                probe_ok = "zenith smoke ok" in probe_path.read_text(encoding="utf-8", errors="replace")
            if results and results[-1][0]["name"] == "implementation":
                if not probe_found:
                    failed.append(f"implementation: probe file missing: {probe_rel}")
                    alternatives = sorted(ROOT.rglob("smoke_probe_*.txt"))
                    if alternatives:
                        print(f"[smoke]   probe files found elsewhere: {[str(p) for p in alternatives[:5]]}")
                elif not probe_ok:
                    failed.append(
                        f"implementation: probe file content mismatch ({probe_path} )"
                    )

            print()
            print("=" * 72)
            print("SMOKE TEST REPORT")
            print("=" * 72)
            print(f"backend   : http://127.0.0.1:{port}  pid={backend.pid}")
            print("            backend console output -> scripts/_diag_backend.log")
            print(f"tui pid   : {pty.pid}")
            print(f"session   : {session_id}")
            print(f"schema budget (gpt-4o/cl100k_base): build={SCHEMA_BUDGET['build']} "
                  f"plan={SCHEMA_BUDGET['plan']} registry={SCHEMA_BUDGET['registry']}")
            for turn, status, summary in results:
                tools = summary["tools"] or ["(none)"]
                confs = f" confirmed={len(summary['confirmations'])}" if summary["confirmations"] else ""
                print(
                    f"  [{turn['name']:15s}] {status:8s} iterations={summary['iterations']} "
                    f"tools={tools}{confs}"
                )
                print(f"        tokens: {fmt_tokens(summary['tokens'])}")
            print(f"probe file: {probe_rel} -> exists={probe_found} content_ok={probe_ok}")
            if failed:
                print("\nASSERTION FAILURES:")
                for f in failed:
                    print(f"  - {f}")
                print("\nRESULT: FAIL")
            else:
                print("\nRESULT: PASS")
            exit_code = 1 if failed else 0
            return exit_code

    except TimeoutError as exc:
        print(f"[smoke] FAIL: {exc}")
        if log is not None:
            _log_tui_tail(log, name="on timeout")
        return 1
    except Exception as exc:
        print(f"[smoke] FAIL: {type(exc).__name__}: {exc}")
        if log is not None:
            _log_tui_tail(log, name="on error")
        return 1
    finally:
        _cleanup(backend, pty, probe_path, keep_probe=((exit_code != 0) or args.keep_probe))


def _resolve_tui_argv() -> list[str]:
    if not PYTHON.exists():
        raise RuntimeError(f"Missing backend interpreter: {PYTHON}")
    if not TSX_CLI.exists():
        raise RuntimeError(f"Missing tsx CLI: {TSX_CLI}")
    node = shutil.which("node") or os.environ.get("NODE") or r"C:\Program Files\nodejs\node.exe"
    if not os.path.exists(node):
        raise RuntimeError(f"node not found: {node}")
    return [node, str(TSX_CLI), "tui/src/index.tsx"]


async def _wait_tui_ready(log: PtyLog) -> None:
    deadline = time.monotonic() + TUI_READY_WAIT
    printed = 0
    while time.monotonic() < deadline:
        text = strip_ansi(log.text())
        if any(m in text for m in TUI_READY_MARKERS):
            return
        elapsed = int(time.monotonic() - (deadline - TUI_READY_WAIT))
        if elapsed > printed and elapsed % 10 == 0:
            printed = elapsed
            print(f"[smoke] waiting for TUI main input ... ({elapsed}s)")
        await asyncio.sleep(0.5)
    tail = strip_ansi(log.text())[-3000:]
    raise TimeoutError(
        "TUI never reached the main input screen.\nCaptured TUI output tail:\n" + (tail or "(empty)")
    )


def _log_tui_tail(log: PtyLog, name: str) -> None:
    tail = strip_ansi(log.text())[-2500:]
    if not tail.strip():
        return
    lines = [l for l in tail.splitlines() if l.strip()]
    print(f"[smoke] TUI output tail {name} ({len(tail)} chars):")
    for line in lines[-12:]:
        print(f"    {line}")


def _cleanup(
    backend: subprocess.Popen | None,
    pty: PtyProcess | None,
    probe_path: Path,
    keep_probe: bool = False,
) -> None:
    if pty is not None:
        try:
            if not pty.terminate(force=False):
                pty.terminate(force=True)
        except Exception:
            pass
        try:
            pty.close(force=True)
        except Exception:
            pass
    if backend is not None and backend.poll() is None:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(backend.pid)],
                capture_output=True,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass
    if not keep_probe and probe_path.exists():
        try:
            probe_path.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
