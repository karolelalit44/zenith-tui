"""
Opens the Zenith TUI in a visible window + sends 'Hi' via WebSocket and logs the response.
You see the app visually AND get a clean log of everything that happened.

Usage:
    python scripts/smoke_test.py
    python scripts/smoke_test.py --prompt "explain compaction"
    python scripts/smoke_test.py --wait 8
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

try:
    import websockets
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
    import websockets


WS_URL = "ws://127.0.0.1:8765/ws"


def ts():
    now = datetime.now()
    return now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}"


def format_event(msg: dict) -> str:
    """Format a single event into a readable line."""
    params = msg.get("params", {})
    kind = params.get("kind", "?")
    data = params.get("data", {})

    if kind == "message":
        return data.get("text", "")
    elif kind == "tool_call":
        tool = data.get("tool", "?")
        p = json.dumps(data.get("params", {}))
        if len(p) > 120:
            p = p[:120] + "..."
        return f"  [{tool}] {p}"
    elif kind == "tool_result":
        tool = data.get("tool", "?")
        ok = data.get("success", "?")
        err = data.get("error", "")
        out = data.get("output", "") or ""
        if err:
            return f"  [{tool}] ERROR: {err[:200]}"
        return f"  [{tool}] OK ({len(out)} chars)"
    elif kind == "error":
        return f"  ERROR: {data.get('message', data)}"
    elif kind == "warning":
        return f"  WARNING: {data.get('message', data)}"
    elif kind == "thinking":
        text = data.get("text", "")
        dur = data.get("duration", 0)
        return f"  [thinking {dur}ms] {text[:200]}"
    elif kind == "progress":
        return f"  ... {data.get('label', '')}"
    elif kind == "turn_manifest":
        return f"  verdict={data.get('verdict', '?')}"
    elif kind == "context_compacted":
        return f"  [compacted] {json.dumps(data)[:150]}"
    else:
        return f"  [{kind}] {json.dumps(data)[:200]}"


async def run(prompt: str, wait: int, response_timeout: int):
    workspace = Path(__file__).resolve().parent.parent
    log_name = f"smoke_test_{time.strftime('%Y%m%d_%H%M%S')}.log"
    log_path = workspace / log_name
    out: list[str] = []

    def log(msg=""):
        line = f"[{ts()}] {msg}" if msg else ""
        out.append(line)
        print(line)

    log("=" * 70)
    log("SMOKE TEST")
    log(f"Prompt : {prompt!r}")
    log(f"Log    : {log_path}")
    log("=" * 70)

    # ── Kill old server ───────────────────────────────────────────────
    log("\n[1] Cleaning up...")
    my_pid = os.getpid()
    try:
        r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                           creationflags=0x08000000)
        for line in r.stdout.splitlines():
            if ":8765" in line and "LISTENING" in line:
                pid = int(line.split()[-1])
                if pid != my_pid:
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True, creationflags=0x08000000)
                    log(f"  Killed old server PID {pid}")
    except Exception:
        pass

    # ── Start backend ─────────────────────────────────────────────────
    log("[2] Starting backend...")
    venv_py = workspace / ".venv" / "Scripts" / "python.exe"
    if not venv_py.exists():
        venv_py = Path(sys.executable)
    server = subprocess.Popen(
        [str(venv_py), "-m", "server.main", "serve"],
        cwd=str(workspace),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=0x08000000,
    )
    log(f"  PID={server.pid}, waiting 4s...")
    await asyncio.sleep(4)

    # ── Open TUI visually ─────────────────────────────────────────────
    log("[3] Opening TUI in new terminal window (for you to see)...")
    tui_cmd = f'cd /d "{workspace}" && title Zenith-SmokeTest && npm run dev:frontend'
    subprocess.Popen(
        ["cmd", "/c", "start", "cmd", "/k", tui_cmd],
        cwd=str(workspace),
    )
    log(f"  Waiting {wait}s for TUI to initialize...")
    await asyncio.sleep(wait)

    # ── Connect via WebSocket ─────────────────────────────────────────
    log("[4] Connecting to backend via WebSocket...")
    async with websockets.connect(WS_URL, max_size=10 * 1024 * 1024) as ws:
        log("  Connected.\n")
        log(f"  > {prompt}")
        log("  " + "-" * 50)

        # Create session
        sid = str(uuid.uuid4())[:8]
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": "s1",
            "method": "session.create",
            "params": {"title": f"smoke-{sid}"},
        }))
        session_id = None
        for _ in range(20):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1)
                msg = json.loads(raw)
                if msg.get("id") == "s1" and "result" in msg:
                    session_id = msg["result"].get("session_id") or msg["result"].get("id")
                    break
            except asyncio.TimeoutError:
                continue

        if not session_id:
            log("  ERROR: session.create failed")
            _save(log_path, out)
            return

        # Send prompt
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": "p1",
            "method": "prompt.send",
            "params": {"content": prompt, "mode": "build", "session_id": session_id},
        }))

        # Collect events
        log("")
        full_answer = []
        start = time.time()
        done = False

        while time.time() - start < response_timeout:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2)
                msg = json.loads(raw)

                if msg.get("method") == "event":
                    line = format_event(msg)
                    if line:
                        log(line)
                    kind = msg.get("params", {}).get("kind", "")
                    text = msg.get("params", {}).get("data", {}).get("text", "")
                    if kind == "message" and text:
                        full_answer.append(text)
                    if kind == "turn_manifest":
                        v = msg["params"]["data"].get("verdict", "")
                        if v in ("completed", "answered"):
                            done = True
                            break

            except asyncio.TimeoutError:
                if done:
                    break
                continue

        elapsed = time.time() - start
        log("  " + "-" * 50)
        log(f"\n  ANSWER ({elapsed:.1f}s):")
        log("  " + "".join(full_answer))
        log("")

    # ── Save ──────────────────────────────────────────────────────────
    _save(log_path, out)
    log(f"Log saved: {log_path}")
    print(f"\n{'='*70}")
    print(f"  LOG: {log_path}")
    print(f"{'='*70}")


def _save(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    p = argparse.ArgumentParser(description="Open TUI + send prompt via WebSocket")
    p.add_argument("--prompt", default="Hi")
    p.add_argument("--wait", type=int, default=10, help="Secs to wait for TUI to load")
    p.add_argument("--response-timeout", type=int, default=120)
    args = p.parse_args()
    asyncio.run(run(args.prompt, args.wait, args.response_timeout))


if __name__ == "__main__":
    main()
