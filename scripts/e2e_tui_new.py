"""
Simple TUI E2E: open a new terminal window, type 3-4 prompts,
watch the responses live, validate via WebSocket.
"""

from __future__ import annotations

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
    safe = msg.encode("ascii", "replace").decode("ascii")
    print(f"[{ts}] {safe}", flush=True)


def screenshot(win, name: str) -> str:
    path = LOG_DIR / f"tui_new_{name}_{time.strftime('%H%M%S')}.png"
    try:
        win.activate()
        time.sleep(0.3)
        img = pyautogui.screenshot(region=(win.left, win.top, win.width, win.height))
        img.save(str(path))
        return str(path)
    except Exception as e:
        log(f"  Screenshot failed: {e}")
        return ""


def type_into_tui(win, text: str) -> None:
    """Click input area, type text, press Enter."""
    win.activate()
    time.sleep(0.4)
    cx = win.left + win.width // 2
    cy = win.top + win.height - 80
    pyautogui.click(cx, cy)
    time.sleep(0.3)
    pyautogui.typewrite(text, interval=0.03)
    time.sleep(0.4)
    pyautogui.press("enter")


async def collect_events(ws, until: str = "success", timeout: int = 60) -> list[dict]:
    """Read WS events until 'success' or 'error' or timeout."""
    events = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            m = json.loads(raw)
            if m.get("method") == "event":
                kind = m.get("params", {}).get("kind", "")
                data = m.get("params", {}).get("data", {})
                events.append({"kind": kind, "data": data})
                if kind in (until, "error"):
                    break
        except asyncio.TimeoutError:
            break
    return events


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Start backend
    log("Starting backend...")
    log_fh = open(LOG_DIR / "backend_tui_new.log", "w", encoding="utf-8")
    backend = subprocess.Popen(
        [sys.executable, "-m", "server.main", "serve"],
        cwd=str(REPO_ROOT), stdout=log_fh, stderr=subprocess.STDOUT,
    )
    log(f"Backend PID: {backend.pid}")

    # 2. Wait for backend
    log("Waiting for backend...")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=3) as r:
                if r.status == 200:
                    break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        log("ERROR: Backend not ready")
        backend.kill()
        return 1
    log("Backend ready")

    # 3. Open TUI in a new visible window
    log("")
    log("=" * 70)
    log("  OPENING TUI IN NEW TERMINAL WINDOW")
    log("=" * 70)
    bat = str(REPO_ROOT / "scripts" / "start_tui.bat")
    subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", bat], shell=False)
    log("Waiting 10s for TUI to load...")
    time.sleep(10)

    # 4. Find TUI window
    win = None
    for _ in range(20):
        for w in gw.getAllWindows():
            if "cmd" in w.title.strip().lower() and w.height > 300:
                win = w
                break
        if win:
            break
        time.sleep(1)

    if not win:
        log("ERROR: TUI window not found")
        backend.kill()
        return 1

    log(f"TUI window: {win.width}x{win.height} at ({win.left},{win.top})")
    ss = screenshot(win, "01_startup")
    log(f"  Startup screenshot: {ss}")

    # 5. Run the test via WebSocket
    import websockets

    async def run() -> dict:
        results: dict = {"passed": [], "failed": [], "transcript": []}

        def ok(n: str) -> None:
            results["passed"].append(n)
            log(f"  PASS  {n}")

        def fail(n: str, r: str = "") -> None:
            results["failed"].append(f"{n}: {r}")
            log(f"  FAIL  {n}: {r}")

        async with websockets.connect("ws://127.0.0.1:8765/ws", max_size=2**22) as ws:
            rpc_id = 0

            async def rpc(method: str, params: dict | None = None, t: int = 15) -> dict:
                nonlocal rpc_id
                rpc_id += 1
                rid = f"r_{rpc_id}"
                msg = {"jsonrpc": "2.0", "id": rid, "method": method}
                if params:
                    msg["params"] = params
                await ws.send(json.dumps(msg))
                dl = time.monotonic() + t
                while time.monotonic() < dl:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=t)
                        m = json.loads(raw)
                        if m.get("id") == rid:
                            return m
                    except asyncio.TimeoutError:
                        break
                return {"error": {"message": "timeout"}}

            async def send_prompt(prompt: str, sid: str, t: int = 60) -> list[dict]:
                nonlocal rpc_id
                rpc_id += 1
                rid = f"p_{rpc_id}"
                await ws.send(json.dumps({
                    "jsonrpc": "2.0", "id": rid, "method": "prompt.send",
                    "params": {"content": prompt, "mode": "build", "session_id": sid},
                }))
                return await collect_events(ws, until="success", timeout=t)

            # Create session
            cr = await rpc("session.create", {"title": "TUI Multi-Prompt Test"})
            sid = cr.get("result", {}).get("id")
            if not sid:
                fail("session.create", str(cr)[:200])
                return results
            ok(f"session.create id={sid[:8]}")

            await rpc("session.resume", {"session_id": sid})

            # Define prompts
            prompts = [
                "What is 2+2?",
                "Now multiply that result by 3.",
                "What is the square root of your last answer?",
                "Now add 100 to that.",
            ]

            for i, prompt in enumerate(prompts):
                log("")
                log(f"--- [{i+1}/{len(prompts)}] Typing: {prompt} ---")

                # Type into TUI
                try:
                    type_into_tui(win, prompt)
                except Exception as e:
                    fail(f"tui.type_{i+1}", str(e))
                    continue

                ss = screenshot(win, f"0{i+2}_typed_{i+1}")
                log(f"  Screenshot: {ss}")

                # Collect response via WS
                events = await send_prompt(prompt, sid, t=60)
                kinds = [e["kind"] for e in events]
                finals = [e for e in events if e["kind"] == "message"
                          and not e.get("data", {}).get("partial")]
                partials = [e for e in events if e["kind"] == "message"
                            and e.get("data", {}).get("partial")]
                response = finals[0]["data"]["text"] if finals else ""
                suc = next((e for e in events if e["kind"] == "success"), None)
                ti = suc["data"].get("tokenInfo", {}) if suc else {}

                log(f"  RECV: {response[:200]}")
                log(f"  TOKENS: {ti.get('used', '?')}/{ti.get('total', '?')}"
                    f" | PARTIALS: {len(partials)} | EVENTS: {kinds}")

                results["transcript"].append({
                    "prompt": prompt, "response": response,
                    "tokens": ti.get("used", 0), "total": ti.get("total", 0),
                    "events": kinds,
                })

                if response:
                    ok(f"prompt_{i+1}.response")
                else:
                    fail(f"prompt_{i+1}.response", "empty")

                if "success" in kinds:
                    ok(f"prompt_{i+1}.success")
                else:
                    fail(f"prompt_{i+1}.success", f"got {kinds}")

                # Wait for TUI rendering to settle
                time.sleep(2)

            # Final screenshot
            time.sleep(3)
            ss = screenshot(win, "06_final")
            log(f"  Final screenshot: {ss}")

            # Cleanup
            await rpc("session.delete", {"session_id": sid})
            ok("session.delete")

            return results

    results = asyncio.run(run())

    # Print summary
    log("")
    log("=" * 70)
    log("RESULTS")
    log("=" * 70)
    for n in results["passed"]:
        log(f"  PASS  {n}")
    for n in results["failed"]:
        log(f"  FAIL  {n}")
    log("")
    log("TRANSCRIPT:")
    log("-" * 70)
    for i, t in enumerate(results["transcript"]):
        log(f"  [{i+1}] SENT:  {t['prompt']}")
        log(f"      RECV:  {t['response'][:150]}")
        log(f"      TOKENS: {t['tokens']}/{t['total']}  EVENTS: {t['events']}")
    log("-" * 70)
    log(f"TOTAL: {len(results['passed'])} passed, {len(results['failed'])} failed")
    log("=" * 70)

    # Save report
    ts = time.strftime("%Y%m%d_%H%M%S")
    report_file = LOG_DIR / f"tui_new_e2e_{ts}.json"
    report_file.write_text(json.dumps({
        "passed": results["passed"], "failed": results["failed"],
        "transcript": results["transcript"],
    }, indent=2, default=str), encoding="utf-8")
    log(f"Report: {report_file}")

    # Close TUI window
    for w in gw.getAllWindows():
        if "cmd" in w.title.strip().lower() and w.height > 300:
            try:
                w.close()
            except Exception:
                pass

    # Kill backend
    log("Shutting down backend...")
    try:
        backend.terminate()
        backend.wait(timeout=5)
    except Exception:
        backend.kill()

    return 1 if results["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
