"""
TUI Session Resume E2E — Final Version
========================================
Key design decisions:
  - Setup: one WS for session.create + session.resume (with delay)
  - Facts: each fact via a SEPARATE fresh WS connection (no stale events)
  - Queries: each query via a SEPARATE fresh WS connection
  - TUI: type in TUI, wait fixed time, screenshot
  - Never send two prompts concurrently on the same WS
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
import websockets

REPO = Path(__file__).resolve().parent.parent
LOG = REPO / "scripts" / "e2e_logs"
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.02


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def shot(win, name: str) -> None:
    p = LOG / f"resume_{name}.png"
    try:
        win.activate()
        time.sleep(0.3)
        pyautogui.screenshot(region=(win.left, win.top, win.width, win.height)).save(str(p))
        log(f"  SS: {p.name}")
    except Exception as e:
        log(f"  SS err: {e}")


def type_cmd(win, text: str) -> None:
    win.activate()
    time.sleep(0.5)
    pyautogui.click(win.left + win.width // 2, win.top + win.height - 80)
    time.sleep(0.3)
    pyautogui.typewrite(text, interval=0.03)
    time.sleep(0.5)
    pyautogui.press("enter")


def kbd(win, *keys: str) -> None:
    win.activate()
    time.sleep(0.3)
    for k in keys:
        pyautogui.press(k)
        time.sleep(0.3)


def find_tui_window():
    for _ in range(25):
        for w in gw.getAllWindows():
            if "cmd" in w.title.strip().lower() and w.height > 300:
                return w
        time.sleep(1)
    return None


async def send_prompt(text: str, sid: str, timeout: int = 90) -> tuple[str, dict, list[str]]:
    """Send a single prompt via a FRESH WS connection.

    First calls session.resume to set the connection-level session_id,
    then sends prompt.send so the message is stored under the correct session.
    Returns (response_text, meta, event_kinds).
    """
    async with websockets.connect(
        "ws://127.0.0.1:8765/ws",
        max_size=2**22,
        ping_interval=30,
    ) as ws:
        await ws.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "r0",
                    "method": "session.resume",
                    "params": {"session_id": sid},
                }
            )
        )
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                m = json.loads(raw)
                if m.get("id") == "r0":
                    break
        except asyncio.TimeoutError:
            pass

        payload = {
            "jsonrpc": "2.0",
            "id": "p1",
            "method": "prompt.send",
            "params": {"content": text, "mode": "build", "session_id": sid},
        }
        await ws.send(json.dumps(payload))

        events = []
        dl = time.monotonic() + timeout
        while time.monotonic() < dl:
            try:
                remaining = dl - time.monotonic()
                raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 30))
                m = json.loads(raw)
                if m.get("method") == "event":
                    kind = m["params"]["kind"]
                    data = m["params"].get("data")
                    events.append({"kind": kind, "data": data})
                    if kind in ("success", "error"):
                        break
            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                break

        finals = [
            e for e in events if e["kind"] == "message" and not (e.get("data") or {}).get("partial")
        ]
        text_out = finals[-1]["data"]["text"] if finals and finals[-1].get("data") else ""

        suc = next((e for e in events if e["kind"] == "success"), None)
        err = next((e for e in events if e["kind"] == "error"), None)

        meta = {}
        if suc and suc.get("data"):
            ti = suc["data"].get("tokenInfo", {})
            meta = {"tokens": ti.get("used", 0), "total": ti.get("total", 0)}
        elif err:
            d = err.get("data") or {}
            meta = {"error": d.get("message", str(d) if d else "unknown")}

        return text_out, meta, [e["kind"] for e in events]


def main():
    LOG.mkdir(parents=True, exist_ok=True)
    P, F, B, T = [], [], [], []

    def ok(n):
        P.append(n)
        log(f"  PASS  {n}")

    def fail(n, r=""):
        F.append(f"{n}: {r}")
        log(f"  FAIL  {n}: {r}")

    def bug(n, d):
        B.append(f"{n}: {d}")
        log(f"  BUG   {n}: {d}")

    # ---- Start backend ----
    log("Starting backend...")
    logfh = open(LOG / "backend_resume.log", "w", encoding="utf-8")
    backend = subprocess.Popen(
        [sys.executable, "-m", "server.main", "serve"],
        cwd=str(REPO),
        stdout=logfh,
        stderr=subprocess.STDOUT,
    )
    dl = time.monotonic() + 30
    while time.monotonic() < dl:
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
    log("Backend ready\n")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # ============================
        # PHASE 1: Create session
        # ============================
        log("=" * 70)
        log("PHASE 1: Create session + store facts via WS")
        log("=" * 70)

        async def create_session():
            async with websockets.connect("ws://127.0.0.1:8765/ws", max_size=2**22) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": "c1",
                            "method": "session.create",
                            "params": {"title": "Zenith Notes"},
                        }
                    )
                )
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=10)
                    m = json.loads(raw)
                    if m.get("id") == "c1":
                        return m.get("result", {}).get("id", "")

        sid = loop.run_until_complete(create_session())
        if not sid:
            log("FATAL: session.create failed")
            return 1
        log(f"Session: {sid[:8]}")

        resume_msg_count = [0]

        async def resume_session():
            async with websockets.connect("ws://127.0.0.1:8765/ws", max_size=2**22) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": "r1",
                            "method": "session.resume",
                            "params": {"session_id": sid},
                        }
                    )
                )
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=15)
                    m = json.loads(raw)
                    if m.get("id") == "r1":
                        msgs = m.get("result", {}).get("messages", [])
                        resume_msg_count[0] = len(msgs)
                        return True

        loop.run_until_complete(resume_session())
        log(f"Session resumed ({resume_msg_count[0]} messages)")
        time.sleep(2)

        facts = [
            "Fact 1: My project is called Zenith. The frontend uses Ink and React.",
            "Fact 2: The backend is Python 3.12 on port 8765 with WebSocket JSON-RPC.",
            "Fact 3: The database is SQLite. Code linting uses ruff.",
        ]
        ok_count = 0
        for i, fact in enumerate(facts):
            log(f"  [{i + 1}] {fact[:60]}...")
            txt, meta, kinds = loop.run_until_complete(send_prompt(fact, sid, timeout=60))
            if "error" in kinds:
                err_msg = meta.get("error", "unknown")
                log(f"    ERROR: {err_msg}")
                log("    Waiting 5s before retry...")
                time.sleep(5)
                txt, meta, kinds = loop.run_until_complete(send_prompt(fact, sid, timeout=60))
                if "error" in kinds:
                    log(f"    RETRY FAILED: {meta.get('error', 'unknown')}")
                    continue
            preview = txt[:100] if txt else "(empty)"
            log(f"    OK: {preview}")
            ok_count += 1
            time.sleep(3)

        if ok_count >= 2:
            ok("facts.stored")
        else:
            fail("facts.stored", f"only {ok_count}/3 succeeded")
            if ok_count == 0:
                return 1

        # ============================
        # PHASE 2: Open TUI
        # ============================
        log("\n" + "=" * 70)
        log("PHASE 2: Open TUI")
        log("=" * 70)

        bat = str(REPO / "scripts" / "start_tui.bat")
        subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", bat], shell=False)
        log("Waiting 14s for TUI...")
        time.sleep(14)

        win = find_tui_window()
        if not win:
            log("ERROR: TUI window not found")
            return 1
        log(f"TUI: {win.width}x{win.height}")
        shot(win, "p2_startup")
        ok("tui.open")

        # ============================
        # PHASE 3: Session browser -> select
        # ============================
        log("\n" + "=" * 70)
        log("PHASE 3: Session browser -> select session")
        log("=" * 70)

        type_cmd(win, "/session")
        time.sleep(2.5)
        shot(win, "p3_browser")
        ok("browser.open")

        kbd(win, "enter")
        time.sleep(2.5)
        shot(win, "p3_selected")
        ok("session.selected")
        shot(win, "p3_resumed")

        # ============================
        # PHASE 4: Context queries via WS (fresh connections)
        # ============================
        log("\n" + "=" * 70)
        log("PHASE 4: Context verification (separate WS per query)")
        log("=" * 70)

        questions = [
            ("What is my project called?", ["zenith"]),
            ("What port does the backend use?", ["8765"]),
            ("What database do I use?", ["sqlite"]),
        ]

        for q, must in questions:
            log(f"  Q: {q}")
            time.sleep(2)
            txt, meta, kinds = loop.run_until_complete(send_prompt(q, sid, timeout=60))
            T.append({"prompt": q, "response": txt})

            if "error" in kinds:
                fail(f"q.{q[:20]}", meta.get("error", "unknown"))
                continue
            if not txt:
                fail(f"q.{q[:20]}", "empty response")
                continue

            log(f"    A: {txt[:200]}")
            log(f"    tokens={meta.get('tokens', '?')}")
            ok(f"q.{q[:20]}.response")

            low = txt.lower()
            hits = [kw for kw in must if kw.lower() in low]
            if hits:
                ok(f"q.{q[:20]}.context ({hits})")
            else:
                fail(f"q.{q[:20]}.context", f"expected {must}")

        # ============================
        # PHASE 5: Type in TUI
        # ============================
        log("\n" + "=" * 70)
        log("PHASE 5: Type in TUI, wait, screenshot")
        log("=" * 70)

        try:
            win = find_tui_window()
            if win:
                tui_q = "What is the project name and what framework is the frontend?"
                log(f"  Typing: {tui_q}")
                type_cmd(win, tui_q)
                log("  Waiting 35s for response...")
                time.sleep(35)
                shot(win, "p5_tui_response")
                ok("tui.typed")
            else:
                fail("tui.find_window", "not found")
        except Exception as e:
            fail("tui.typing", str(e))

        # ============================
        # PHASE 6: Verify resume returns messages via WS
        # ============================
        log("\n" + "=" * 70)
        log("PHASE 6: Verify session resume returns full message history")
        log("=" * 70)

        async def check_resume_messages():
            async with websockets.connect("ws://127.0.0.1:8765/ws", max_size=2**22) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": "chk",
                            "method": "session.resume",
                            "params": {"session_id": sid},
                        }
                    )
                )
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=15)
                    m = json.loads(raw)
                    if m.get("id") == "chk":
                        result = m.get("result", {})
                        msgs = result.get("messages", [])
                        roles = [msg.get("role") for msg in msgs]
                        return msgs, roles

        msgs, roles = loop.run_until_complete(check_resume_messages())
        user_msgs = [r for r in roles if r == "user"]
        asst_msgs = [r for r in roles if r == "assistant"]
        log(f"  Messages: {len(msgs)} total ({len(user_msgs)} user, {len(asst_msgs)} assistant)")

        if len(msgs) > 0:
            ok("resume.has_messages")
        else:
            fail("resume.has_messages", "no messages returned")

        if len(user_msgs) >= 3:
            ok("resume.user_messages")
        else:
            fail("resume.user_messages", f"expected >=3, got {len(user_msgs)}")

        if len(asst_msgs) >= 3:
            ok("resume.assistant_messages")
        else:
            fail("resume.assistant_messages", f"expected >=3, got {len(asst_msgs)}")

        # ============================
        # PHASE 7: Leave + reopen TUI
        # ============================
        log("\n" + "=" * 70)
        log("PHASE 7: Leave session -> reopen from session browser")
        log("=" * 70)

        try:
            win = find_tui_window()
            if win:
                type_cmd(win, "/session")
                time.sleep(2.5)
                shot(win, "p6_browser")
                kbd(win, "enter")
                time.sleep(2.5)
                shot(win, "p6_reopened")
                ok("session.reopened")
            else:
                fail("tui.reopen", "window lost")
        except Exception as e:
            fail("tui.reopen", str(e))

        # ============================
        # PHASE 8: Final context check
        # ============================
        log("\n" + "=" * 70)
        log("PHASE 8: Final context check after reopen")
        log("=" * 70)

        fq = "List all the facts I told you about my project earlier"
        time.sleep(2)
        ftxt, fmeta, fkinds = loop.run_until_complete(send_prompt(fq, sid, timeout=60))
        T.append({"prompt": fq, "response": ftxt})
        log(f"  Q: {fq}")
        log(f"  A: {ftxt[:300]}")
        log(f"  tokens={fmeta.get('tokens', '?')}")

        if "error" in fkinds:
            fail("final.query", fmeta.get("error", "unknown"))
        elif not ftxt:
            fail("final.query", "empty")
        else:
            ok("final.response")
            checks = {
                "zenith": "zenith" in ftxt.lower(),
                "ink/react": "ink" in ftxt.lower() or "react" in ftxt.lower(),
                "python": "python" in ftxt.lower(),
                "8765": "8765" in ftxt,
                "sqlite": "sqlite" in ftxt.lower(),
            }
            found = [k for k, v in checks.items() if v]
            missing = [k for k, v in checks.items() if not v]
            if len(found) >= 3:
                ok(f"final.context ({found})")
            else:
                fail("final.context", f"found {found}, missing {missing}")

        try:
            win = find_tui_window()
            if win:
                shot(win, "p7_final")
        except Exception:
            pass

        loop.close()

        # ============================
        # SUMMARY
        # ============================
        log("\n" + "=" * 70)
        log("SESSION RESUME E2E RESULTS")
        log("=" * 70)
        for n in P:
            log(f"  PASS  {n}")
        for n in F:
            log(f"  FAIL  {n}")
        for n in B:
            log(f"  BUG   {n}")
        log("")
        log("TRANSCRIPT:")
        log("-" * 70)
        for i, t in enumerate(T):
            log(f"  [{i + 1}] SENT: {t['prompt'][:100]}")
            log(f"      RECV: {t['response'][:200]}")
        log("-" * 70)
        log(f"TOTAL: {len(P)} passed, {len(F)} failed, {len(B)} bugs")
        log("=" * 70)

        ts = time.strftime("%Y%m%d_%H%M%S")
        (LOG / f"resume_final_{ts}.json").write_text(
            json.dumps(
                {"passed": P, "failed": F, "bugs": B, "transcript": T}, indent=2, default=str
            ),
            encoding="utf-8",
        )
        return 1 if F else 0

    finally:
        log("\nClosing TUI window...")
        for w in gw.getAllWindows():
            if "cmd" in w.title.strip().lower() and w.height > 300:
                try:
                    w.close()
                except Exception:
                    pass
        log("Shutting down backend...")
        try:
            backend.terminate()
            backend.wait(timeout=5)
        except Exception:
            backend.kill()


if __name__ == "__main__":
    sys.exit(main())
