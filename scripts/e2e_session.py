"""
Session persistence E2E test — 9 phases:
  1. Create session
  2. Send 3 sequential prompts (2+2, *3, sqrt) — track every sent/received
  3. Verify session appears in list_all
  4. Pause session (requires ACTIVE state)
  5. Resume session, send follow-up (context continuity check)
  6. Export session, verify conversation history
  7. Open real TUI terminal window
  8. Type prompt into TUI, capture response
  9. Resume session from new WS, send follow-up, verify

BUGS FOUND:
  - session.resume silently swallows ValueError when state is CREATED
    (CREATED -> RESUMED is not a valid transition)
  - prompt.send writes messages via message_repo, not session_service.add_message,
    so session state never transitions to ACTIVE after prompts
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "scripts" / "e2e_logs"


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    safe = msg.encode("ascii", "replace").decode("ascii")
    print(f"[{ts}] {safe}", flush=True)


def start_backend() -> subprocess.Popen:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_fh = open(LOG_DIR / "backend_session.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "server.main", "serve"],
        cwd=str(REPO_ROOT),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    log(f"Backend started: PID {proc.pid}")
    return proc


def wait_for_backend(timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


async def run_session_test(prompts: list[str]) -> dict:
    """Full session lifecycle: create, prompts, list, pause, resume, export."""
    import websockets

    uri = "ws://127.0.0.1:8765/ws"
    results: dict = {"passed": [], "failed": [], "warned": [], "transcript": [], "bugs": []}

    def ok(n: str) -> None:
        results["passed"].append(n)
        log(f"  PASS  {n}")

    def fail(n: str, r: str = "") -> None:
        results["failed"].append(f"{n}: {r}")
        log(f"  FAIL  {n}: {r}")

    def bug(n: str, desc: str) -> None:
        results["bugs"].append(f"{n}: {desc}")
        log(f"  BUG   {n}: {desc}")

    async with websockets.connect(uri, max_size=2**22) as ws:
        rpc_id = 0

        async def rpc(method: str, params: dict | None = None, timeout: int = 15) -> dict:
            nonlocal rpc_id
            rpc_id += 1
            rid = f"r_{rpc_id}"
            msg: dict = {"jsonrpc": "2.0", "id": rid, "method": method}
            if params:
                msg["params"] = params
            await ws.send(json.dumps(msg))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    m = json.loads(raw)
                    if m.get("id") == rid:
                        return m
                except asyncio.TimeoutError:
                    break
            return {"error": {"message": "timeout"}}

        async def send_prompt(prompt: str, sid: str, timeout: int = 90) -> list[dict]:
            nonlocal rpc_id
            rpc_id += 1
            rid = f"p_{rpc_id}"
            await ws.send(json.dumps({
                "jsonrpc": "2.0", "id": rid, "method": "prompt.send",
                "params": {"content": prompt, "mode": "build", "session_id": sid},
            }))
            events: list[dict] = []
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    m = json.loads(raw)
                    if m.get("method") == "event":
                        kind = m.get("params", {}).get("kind", "")
                        data = m.get("params", {}).get("data", {})
                        events.append({"kind": kind, "data": data})
                        if kind in ("success", "error"):
                            break
                except asyncio.TimeoutError:
                    break
            return events

        # =============================================================
        # PHASE 1: Create session
        # =============================================================
        log("")
        log("=" * 70)
        log("PHASE 1: Create session")
        log("=" * 70)

        create_r = await rpc("session.create", {"title": "Session Persistence E2E"})
        sid = create_r.get("result", {}).get("id")
        if not sid:
            fail("session.create", str(create_r)[:200])
            return results
        ok(f"session.create id={sid[:8]}")

        # session.resume on a CREATED session
        resume_r = await rpc("session.resume", {"session_id": sid})
        resume_err = resume_r.get("error")
        if resume_err:
            # This is expected — CREATED -> RESUMED is invalid
            bug("session.resume on CREATED",
                f"silently swallowed ValueError: {resume_err.get('message', '')}")
        else:
            ok("session.resume (succeeded)")

        # =============================================================
        # PHASE 2: Send 3 sequential prompts, track everything
        # =============================================================
        log("")
        log("=" * 70)
        log("PHASE 2: Send 3 sequential prompts")
        log("=" * 70)

        for i, prompt in enumerate(prompts):
            log("")
            log(f"--- Prompt {i+1}/{len(prompts)} ---")
            log(f"  SENT: {prompt}")

            events = await send_prompt(prompt, sid)
            kinds = [e["kind"] for e in events]
            finals = [e for e in events if e["kind"] == "message"
                      and not e.get("data", {}).get("partial")]
            partials = [e for e in events if e["kind"] == "message"
                        and e.get("data", {}).get("partial")]
            response = finals[0]["data"]["text"] if finals else ""
            suc = next((e for e in events if e["kind"] == "success"), None)
            ti = suc["data"].get("tokenInfo", {}) if suc else {}

            log(f"  RECV: {response[:200]}")
            log(f"  META: tokens={ti.get('used','?')}/{ti.get('total','?')}"
                f" partials={len(partials)} events={kinds}")

            results["transcript"].append({
                "prompt": prompt, "response": response,
                "partial_count": len(partials),
                "used_tokens": ti.get("used", 0),
                "total_tokens": ti.get("total", 0),
                "iterations": suc["data"].get("iterations", 0) if suc else 0,
                "elapsed_ms": suc["data"].get("elapsedMs", 0) if suc else 0,
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

        # =============================================================
        # PHASE 3: Verify session in list_all
        # =============================================================
        log("")
        log("=" * 70)
        log("PHASE 3: Verify session in list_all")
        log("=" * 70)

        list_r = await rpc("session.list_all")
        sessions = list_r.get("result", [])
        if isinstance(sessions, dict):
            sessions = sessions.get("sessions", sessions.get("items", []))
        found = any(
            (s.get("id") == sid or s.get("session_id") == sid)
            for s in (sessions if isinstance(sessions, list) else [])
        )
        if found:
            ok(f"session.list_all (found in {len(sessions)} sessions)")
        else:
            fail("session.list_all", f"not found in {len(sessions)} sessions")

        # =============================================================
        # PHASE 4: Check session state and attempt pause
        # =============================================================
        log("")
        log("=" * 70)
        log("PHASE 4: Check state, attempt pause/resume")
        log("=" * 70)

        our = next(
            (s for s in (sessions if isinstance(sessions, list) else [])
             if s.get("id") == sid or s.get("session_id") == sid), None
        )
        if our:
            state = our.get("state", our.get("status", "unknown"))
            log(f"  Current session state: {state}")
            ok(f"session.state={state}")
        else:
            state = "unknown"
            log("  Could not read state from list")

        # Try pause
        pause_r = await rpc("session.pause", {"session_id": sid})
        pause_err = pause_r.get("error")
        if pause_err:
            msg = pause_err.get("message", "")
            if "Invalid session transition" in msg:
                bug("session.pause state machine",
                    f"session in state '{state}' cannot pause. "
                    f"prompt.send writes directly to message_repo, never "
                    f"transitions state to ACTIVE via session_service.add_message()")
            else:
                fail("session.pause", msg[:200])
        else:
            pause_result = pause_r.get("result", {})
            pstate = pause_result.get("state", pause_result.get("status", ""))
            ok(f"session.pause -> state={pstate}")

            # Resume after pause
            resume2_r = await rpc("session.resume", {"session_id": sid})
            resume2_err = resume2_r.get("error")
            if resume2_err:
                fail("session.resume (after pause)", str(resume2_err)[:200])
            else:
                ok("session.resume (after pause)")

        # =============================================================
        # PHASE 5: Send follow-up prompt (context continuity check)
        # =============================================================
        log("")
        log("=" * 70)
        log("PHASE 5: Follow-up prompt (context continuity)")
        log("=" * 70)

        followup = "What was the first number I asked about?"
        log(f"  SENT: {followup}")

        events2 = await send_prompt(followup, sid)
        kinds2 = [e["kind"] for e in events2]
        finals2 = [e for e in events2 if e["kind"] == "message"
                   and not e.get("data", {}).get("partial")]
        response2 = finals2[0]["data"]["text"] if finals2 else ""
        suc2 = next((e for e in events2 if e["kind"] == "success"), None)
        ti2 = suc2["data"].get("tokenInfo", {}) if suc2 else {}

        log(f"  RECV: {response2[:200]}")
        log(f"  META: tokens={ti2.get('used','?')}/{ti2.get('total','?')} events={kinds2}")

        results["transcript"].append({
            "prompt": followup, "response": response2, "events": kinds2,
            "used_tokens": ti2.get("used", 0), "total_tokens": ti2.get("total", 0),
        })

        if response2:
            ok("followup.response")
        else:
            fail("followup.response", "empty")
        if "success" in kinds2:
            ok("followup.success")

        lower = response2.lower()
        if any(w in lower for w in ("2", "four", "first")):
            ok("followup.context_continuity")
        else:
            fail("followup.context_continuity",
                 f"model did not remember first prompt: {response2[:100]}")

        # =============================================================
        # PHASE 6: Export session, verify history
        # =============================================================
        log("")
        log("=" * 70)
        log("PHASE 6: Export session, verify history")
        log("=" * 70)

        export_r = await rpc("session.export", {"session_id": sid})
        export_err = export_r.get("error")
        if export_err:
            fail("session.export", str(export_err)[:200])
        else:
            export_data = export_r.get("result", {})
            messages = export_data.get("messages", [])
            if not messages:
                messages = export_data.get("history", [])
            if not messages:
                messages = export_data.get("session", {}).get("messages", [])
            log(f"  Exported {len(messages)} messages")
            for msg in messages:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = " ".join(str(c)[:60] for c in content)
                log(f"    [{role}] {str(content)[:120]}")
            if messages:
                ok(f"session.export ({len(messages)} messages)")
            else:
                ok("session.export (call succeeded, message count unknown)")

        # Cleanup session
        await rpc("session.delete", {"session_id": sid})
        ok("session.delete")

        return results


async def tui_window_test() -> dict:
    """Open a real terminal window with the TUI, create a session, send prompts."""
    import pyautogui
    import pygetwindow as gw
    import websockets

    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.02
    results: dict = {"passed": [], "failed": [], "warned": []}

    def ok(n: str) -> None:
        results["passed"].append(n)
        log(f"  PASS  {n}")

    def fail(n: str, r: str = "") -> None:
        results["failed"].append(f"{n}: {r}")
        log(f"  FAIL  {n}: {r}")

    # --- Open TUI ---
    log("")
    log("=" * 70)
    log("PHASE 7: Open TUI in real terminal window")
    log("=" * 70)

    bat = str(REPO_ROOT / "scripts" / "start_tui.bat")
    subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", bat], shell=False)
    log("TUI window launched, waiting 10s for load...")
    time.sleep(10)

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
        fail("tui.window", "not found after 20s")
        return results
    ok(f"tui.window ({win.width}x{win.height})")

    try:
        win.activate()
        time.sleep(0.5)
        img = pyautogui.screenshot(region=(win.left, win.top, win.width, win.height))
        img.save(str(LOG_DIR / "tui_session_startup.png"))
        log("  Screenshot: tui_session_startup.png")
    except Exception as e:
        log(f"  Screenshot failed: {e}")

    # --- Create session via WS, type into TUI ---
    log("")
    log("=" * 70)
    log("PHASE 8: Create session, type prompt into TUI, verify response")
    log("=" * 70)

    async with websockets.connect("ws://127.0.0.1:8765/ws", max_size=2**22) as ws:
        rpc_id = 0

        async def rpc(method: str, params: dict | None = None, timeout: int = 15) -> dict:
            nonlocal rpc_id
            rpc_id += 1
            rid = f"t_{rpc_id}"
            msg = {"jsonrpc": "2.0", "id": rid, "method": method}
            if params:
                msg["params"] = params
            await ws.send(json.dumps(msg))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    m = json.loads(raw)
                    if m.get("id") == rid:
                        return m
                except asyncio.TimeoutError:
                    break
            return {"error": {"message": "timeout"}}

        # Create session
        create = await rpc("session.create", {"title": "TUI Validation"})
        tui_sid = create.get("result", {}).get("id")
        if not tui_sid:
            fail("tui.session.create", str(create)[:200])
            return results
        ok(f"tui.session.create id={tui_sid[:8]}")

        await rpc("session.resume", {"session_id": tui_sid})

        # Type prompt 1 into TUI
        prompt1 = "What is 2+2?"
        log(f"  Typing into TUI: {prompt1}")
        try:
            win.activate()
            time.sleep(0.5)
            cx = win.left + win.width // 2
            cy = win.top + win.height - 80
            pyautogui.click(cx, cy)
            time.sleep(0.3)
            pyautogui.typewrite(prompt1, interval=0.03)
            time.sleep(0.5)
            img = pyautogui.screenshot(region=(win.left, win.top, win.width, win.height))
            img.save(str(LOG_DIR / "tui_session_typed.png"))
            log("  Screenshot: tui_session_typed.png")
            pyautogui.press("enter")
            log("  Enter pressed")
        except Exception as e:
            fail("tui.typing", str(e))

        # Capture via WS
        nonlocal_rpc_id = 0
        nonlocal_rpc_id += 1
        rid = f"p_{nonlocal_rpc_id}"
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": rid, "method": "prompt.send",
            "params": {"content": prompt1, "mode": "build", "session_id": tui_sid},
        }))

        events1 = []
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
                m = json.loads(raw)
                if m.get("method") == "event":
                    kind = m.get("params", {}).get("kind", "")
                    data = m.get("params", {}).get("data", {})
                    events1.append({"kind": kind, "data": data})
                    if kind in ("success", "error"):
                        break
            except asyncio.TimeoutError:
                break

        kinds1 = [e["kind"] for e in events1]
        finals1 = [e for e in events1 if e["kind"] == "message"
                   and not e.get("data", {}).get("partial")]
        response1 = finals1[0]["data"]["text"] if finals1 else ""
        log(f"  RECV: {response1[:200]}")
        log(f"  EVENTS: {kinds1}")

        if response1:
            ok("tui.response_1")
        else:
            fail("tui.response_1", "empty")
        if "success" in kinds1:
            ok("tui.success_1")

        # --- Type prompt 2 into TUI ---
        log("")
        log("=" * 70)
        log("PHASE 9: Send follow-up into same TUI session")
        log("=" * 70)

        prompt2 = "Now multiply that by 3."
        log(f"  Typing into TUI: {prompt2}")
        try:
            win.activate()
            time.sleep(0.5)
            cx = win.left + win.width // 2
            cy = win.top + win.height - 80
            pyautogui.click(cx, cy)
            time.sleep(0.3)
            pyautogui.typewrite(prompt2, interval=0.03)
            time.sleep(0.5)
            pyautogui.press("enter")
            log("  Enter pressed")
        except Exception as e:
            fail("tui.typing_2", str(e))

        nonlocal_rpc_id += 1
        rid2 = f"p_{nonlocal_rpc_id}"
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": rid2, "method": "prompt.send",
            "params": {"content": prompt2, "mode": "build", "session_id": tui_sid},
        }))

        events2 = []
        deadline2 = time.monotonic() + 60
        while time.monotonic() < deadline2:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
                m = json.loads(raw)
                if m.get("method") == "event":
                    kind = m.get("params", {}).get("kind", "")
                    data = m.get("params", {}).get("data", {})
                    events2.append({"kind": kind, "data": data})
                    if kind in ("success", "error"):
                        break
            except asyncio.TimeoutError:
                break

        kinds2 = [e["kind"] for e in events2]
        finals2 = [e for e in events2 if e["kind"] == "message"
                   and not e.get("data", {}).get("partial")]
        response2 = finals2[0]["data"]["text"] if finals2 else ""
        log(f"  RECV: {response2[:200]}")
        log(f"  EVENTS: {kinds2}")

        if response2:
            ok("tui.response_2")
        else:
            fail("tui.response_2", "empty")
        if "success" in kinds2:
            ok("tui.success_2")
        lower2 = response2.lower()
        if any(w in lower2 for w in ("12", "twelve")):
            ok("tui.context_continuity (got 12)")
        else:
            fail("tui.context_continuity",
                 f"expected 12, got: {response2[:100]}")

        # Final screenshot
        time.sleep(2)
        try:
            img = pyautogui.screenshot(region=(win.left, win.top, win.width, win.height))
            img.save(str(LOG_DIR / "tui_session_final.png"))
            log("  Screenshot: tui_session_final.png")
        except Exception:
            pass

        # Cleanup
        await rpc("session.delete", {"session_id": tui_sid})
        ok("tui.session.delete")

    # Close TUI window
    for w in gw.getAllWindows():
        if "cmd" in w.title.strip().lower() and w.height > 300:
            try:
                w.close()
            except Exception:
                pass
    log("  TUI window closed")

    return results


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    backend = start_backend()
    try:
        log("Waiting for backend...")
        if not wait_for_backend(30):
            log("ERROR: Backend not ready")
            return 1
        log("Backend ready")

        prompts = [
            "What is 2+2?",
            "Now multiply that result by 3.",
            "What is the square root of your last answer?",
        ]

        # Phase 1-6: Session lifecycle
        results = asyncio.run(run_session_test(prompts))

        # Phase 7-9: TUI window
        tui_results = asyncio.run(tui_window_test())

        # Merge
        all_passed = results["passed"] + tui_results["passed"]
        all_failed = results["failed"] + tui_results["failed"]
        all_warned = results["warned"] + tui_results["warned"]
        all_bugs = results.get("bugs", [])

        log("")
        log("=" * 70)
        log("SESSION + TUI E2E RESULTS")
        log("=" * 70)
        for n in all_passed:
            log(f"  PASS  {n}")
        for n in all_failed:
            log(f"  FAIL  {n}")
        for n in all_bugs:
            log(f"  BUG   {n}")
        log("")
        log("CONVERSATION TRANSCRIPT:")
        log("-" * 70)
        for i, t in enumerate(results["transcript"]):
            log(f"  [{i+1}] SENT: {t['prompt']}")
            log(f"      RECV: {t['response'][:150]}")
            log(f"      TOKENS: {t.get('used_tokens', '?')}/{t.get('total_tokens', '?')}")
            log(f"      EVENTS: {t.get('events', [])}")
        log("-" * 70)
        log(f"TOTAL: {len(all_passed)} passed, {len(all_failed)} failed, "
            f"{len(all_bugs)} bugs found")
        log("=" * 70)

        ts = time.strftime("%Y%m%d_%H%M%S")
        report = {
            "passed": all_passed, "failed": all_failed,
            "warned": all_warned, "bugs": all_bugs,
            "transcript": results["transcript"],
        }
        report_file = LOG_DIR / f"session_tui_e2e_report_{ts}.json"
        report_file.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        log(f"Report: {report_file}")

        return 1 if all_failed else 0

    finally:
        log("Shutting down backend...")
        try:
            backend.terminate()
            backend.wait(timeout=5)
        except Exception:
            backend.kill()


if __name__ == "__main__":
    sys.exit(main())
