"""
E2E TUI test — opens a REAL visible terminal window with the TUI,
types a prompt, watches the response, then analyzes everything.

You can WATCH the TUI run in its own window.

Usage:
    python scripts/e2e_tui.py
    python scripts/e2e_tui.py --prompt "What is 2+2?"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pyautogui
import pygetwindow as gw

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "scripts" / "e2e_logs"
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.02


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def start_backend() -> subprocess.Popen:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_fh = open(LOG_DIR / "backend_tui.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "server.main", "serve"],
        cwd=str(REPO_ROOT),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    log(f"Backend started: PID {proc.pid}")
    return proc


def wait_for_backend(timeout: float) -> bool:
    url = "http://127.0.0.1:8765/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def open_tui_window() -> None:
    """Open the TUI in a NEW visible terminal window via bat file."""
    bat = str(REPO_ROOT / "scripts" / "start_tui.bat")
    subprocess.Popen(
        ["cmd", "/c", "start", "cmd", "/k", bat],
        shell=False,
    )
    time.sleep(3)


def find_tui_window() -> gw.Win32Window | None:
    """Find the TUI window -- a cmd.exe window that is large enough."""
    for _ in range(30):
        for w in gw.getAllWindows():
            t = w.title.strip()
            if not t:
                continue
            if "cmd" in t.lower() and w.height > 300:
                return w
        time.sleep(1)
    return None


def take_screenshot(window: gw.Win32Window, name: str) -> str:
    """Take a screenshot of the window and save it."""
    path = LOG_DIR / f"tui_{name}_{time.strftime('%H%M%S')}.png"
    try:
        window.activate()
        time.sleep(0.3)
        x, y, ww, hh = window.left, window.top, window.width, window.height
        img = pyautogui.screenshot(region=(x, y, ww, hh))
        img.save(str(path))
        return str(path)
    except Exception as e:
        log(f"Screenshot failed: {e}")
        return ""


async def ws_validate(prompt: str, timeout: int) -> dict:
    """Validate everything via WebSocket protocol."""
    uri = "ws://127.0.0.1:8765/ws"
    results: dict[str, list[str]] = {"passed": [], "failed": [], "warned": []}

    def ok(n: str) -> None:
        results["passed"].append(n)
        log(f"  PASS  {n}")

    def fail(n: str, r: str = "") -> None:
        results["failed"].append(f"{n}: {r}")
        log(f"  FAIL  {n}: {r}")

    def warn(n: str, m: str = "") -> None:
        results["warned"].append(f"{n}: {m}")
        log(f"  WARN  {n}: {m}")

    import websockets

    async with websockets.connect(uri, max_size=2**22) as ws:
        rpc_id = 0

        async def rpc(method: str, params: dict | None = None, rpc_timeout: int = 15) -> dict:
            nonlocal rpc_id
            rpc_id += 1
            rid = f"t_{rpc_id}"
            msg: dict = {"jsonrpc": "2.0", "id": rid, "method": method}
            if params:
                msg["params"] = params
            await ws.send(json.dumps(msg))
            deadline = time.monotonic() + rpc_timeout
            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=rpc_timeout)
                    m = json.loads(raw)
                    if m.get("id") == rid:
                        return m
                except asyncio.TimeoutError:
                    break
            return {"error": {"message": "timeout"}}

        async def stream_until(
            method: str, params: dict, until_kind: str, stream_timeout: int = 90
        ) -> list[dict]:
            nonlocal rpc_id
            rpc_id += 1
            rid = f"s_{rpc_id}"
            msg = {"jsonrpc": "2.0", "id": rid, "method": method}
            if params:
                msg["params"] = params
            await ws.send(json.dumps(msg))
            events: list[dict] = []
            deadline = time.monotonic() + stream_timeout
            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=stream_timeout)
                    m = json.loads(raw)
                    if m.get("method") == "event":
                        kind = m.get("params", {}).get("kind", "")
                        data = m.get("params", {}).get("data", {})
                        events.append({"kind": kind, "data": data})
                        if kind == until_kind:
                            return events
                        if kind == "error":
                            return events
                except asyncio.TimeoutError:
                    break
            return events

        # Create a fresh session
        create = await rpc("session.create", {"title": "TUI Window E2E"})
        sid = create.get("result", {}).get("id")
        if sid:
            ok("session.create")
        else:
            fail("session.create", str(create))
            return results

        resume = await rpc("session.resume", {"session_id": sid})
        if resume.get("result"):
            ok("session.resume")

        # Send prompt and stream
        log("Sending prompt via WebSocket...")
        events = await stream_until(
            "prompt.send",
            {"content": prompt, "mode": "build", "session_id": sid},
            "success",
            timeout,
        )

        kinds = [e["kind"] for e in events]
        log(f"Events received: {kinds}")

        # --- Validate events ---
        for k in ["message", "success"]:
            if k in kinds:
                ok(f"event.{k}")
            else:
                fail(f"event.{k}", f"not in {kinds}")

        for k in ["turn_manifest", "thinking", "tool_call", "tool_result", "warning"]:
            if k in kinds:
                ok(f"event.{k}")
            else:
                warn(f"event.{k}", "not emitted")

        # Streaming
        partials = [e for e in events if e["kind"] == "message" and e.get("data", {}).get("partial")]
        finals = [e for e in events if e["kind"] == "message" and not e.get("data", {}).get("partial")]
        if partials:
            ok(f"streaming.partials ({len(partials)})")
        else:
            warn("streaming.partials", "none")
        if finals:
            ok("streaming.final")
            text = finals[0].get("data", {}).get("text", "")
            log(f"Response: {text[:200]}...")
        else:
            fail("streaming.final", "none")

        # Success event
        suc = next((e for e in events if e["kind"] == "success"), None)
        if suc:
            sd = suc.get("data", {})
            for f in ["message", "iterations", "elapsedMs"]:
                if f in sd:
                    ok(f"success.{f}")
                else:
                    fail(f"success.{f}", f"missing from {list(sd.keys())}")

            ti = sd.get("tokenInfo", {})
            if ti:
                ok("success.tokenInfo")
                for f in ["used", "remaining", "total", "percent"]:
                    if f in ti:
                        ok(f"tokenInfo.{f}")
                    else:
                        fail(f"tokenInfo.{f}", "missing")
                if "tierBreakdown" in ti or "tierBreakdown" in sd:
                    ok("success.tierBreakdown")
                if "stale_reads_evicted" in ti:
                    ok("success.stale_reads_evicted")
                if "cache_hit_rate" in ti:
                    ok("success.cache_hit_rate")
            else:
                fail("success.tokenInfo", "missing")
        else:
            fail("success.event", "not found")

        # Manifest
        manifest = next((e for e in events if e["kind"] == "turn_manifest"), None)
        if manifest:
            md = manifest.get("data", {})
            for f in ["created", "modified", "remaining", "completed", "stalled"]:
                if f in md:
                    ok(f"manifest.{f}")
                else:
                    fail(f"manifest.{f}", "missing")
        else:
            warn("manifest", "not emitted")

        # Cleanup
        await rpc("session.delete", {"session_id": sid})

        return results


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E TUI window test")
    parser.add_argument("--prompt", default="What is 2+2? Reply with just the number.")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Start backend
    backend = start_backend()
    try:
        log("Waiting for backend...")
        if not wait_for_backend(30):
            log("ERROR: Backend failed to start")
            return 1
        log("Backend ready")

        # 2. Open TUI in a visible window
        log("")
        log("=" * 70)
        log("  OPENING TUI IN A NEW TERMINAL WINDOW...")
        log("  You should see it appear on your screen!")
        log("=" * 70)
        open_tui_window()

        # 3. Find the window
        log("Looking for TUI window...")
        win = find_tui_window()

        if not win:
            log("ERROR: Could not find TUI window")
            return 1

        log(f"Found TUI window: {win.title} ({win.width}x{win.height} at {win.left},{win.top})")

        # 4. Wait for TUI to fully load
        log("Waiting for TUI to fully load (5s)...")
        time.sleep(5)

        # Take initial screenshot
        ss1 = take_screenshot(win, "startup")
        if ss1:
            log(f"Startup screenshot: {ss1}")

        # 5. Activate the window and type the prompt
        log("Activating TUI window...")
        try:
            win.activate()
        except Exception:
            pass
        time.sleep(0.5)

        # Click on the input area (bottom of window)
        cx = win.left + win.width // 2
        cy = win.top + win.height - 80
        pyautogui.click(cx, cy)
        time.sleep(0.3)

        # Type the prompt
        log(f"Typing prompt: {args.prompt}")
        pyautogui.typewrite(args.prompt, interval=0.03)
        time.sleep(0.5)

        # Take screenshot after typing
        ss2 = take_screenshot(win, "typed")
        if ss2:
            log(f"After typing screenshot: {ss2}")

        # 6. Press Enter to submit
        log("Pressing Enter...")
        pyautogui.press("enter")

        # 7. Wait for response
        log("Waiting for response (15s)...")
        time.sleep(15)

        # 8. Take final screenshot
        time.sleep(2)
        ss_final = take_screenshot(win, "final")
        log(f"Final screenshot: {ss_final}")

        # 9. Validate via WebSocket
        log("")
        log("=" * 70)
        log("VALIDATING VIA WEBSOCKET PROTOCOL")
        log("=" * 70)

        results = asyncio.run(ws_validate(args.prompt, args.timeout))

        # Print results
        log("")
        log("=" * 70)
        log("TUI WINDOW E2E RESULTS")
        log("=" * 70)
        for n in results["passed"]:
            log(f"  PASS  {n}")
        for n in results["failed"]:
            log(f"  FAIL  {n}")
        for n in results["warned"]:
            log(f"  WARN  {n}")
        log("")
        log(f"Total: {len(results['passed'])} passed, {len(results['failed'])} failed, {len(results['warned'])} warned")
        log("=" * 70)

        # Save report
        ts = time.strftime("%Y%m%d_%H%M%S")
        report = {
            "passed": results["passed"],
            "failed": results["failed"],
            "warned": results["warned"],
            "screenshots": [str(p) for p in LOG_DIR.glob("tui_*.png")],
            "prompt": args.prompt,
        }
        report_file = LOG_DIR / f"tui_e2e_report_{ts}.json"
        report_file.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        log(f"Report saved: {report_file}")

        return 1 if results["failed"] else 0

    finally:
        # Kill the TUI window
        log("Closing TUI window...")
        for w in gw.getAllWindows():
            if "cmd" in w.title.strip().lower() and w.height > 300:
                try:
                    w.close()
                    log(f"Closed window: {w.title}")
                except Exception:
                    try:
                        w.kill()
                    except Exception:
                        pass

        log(f"Shutting down backend (PID {backend.pid})...")
        try:
            backend.terminate()
            backend.wait(timeout=5)
        except Exception:
            backend.kill()


if __name__ == "__main__":
    sys.exit(main())
