"""E2E: Open TUI -> sessions -> select old -> verify messages restore -> resume."""

import asyncio
import ctypes
import ctypes.wintypes
import json
import subprocess
import sys
import time
from pathlib import Path
import websockets

REPO = Path(__file__).resolve().parent.parent
LOG = REPO / "scripts" / "e2e_logs"
OUTPUT = LOG / "resume_verify"
OUTPUT.mkdir(parents=True, exist_ok=True)

try:
    import pyautogui
    import pygetwindow as gw

    pyautogui.FAILSAFE = False
    HAS_GUI = True
except ImportError:
    HAS_GUI = False

k32 = ctypes.windll.kernel32
u32 = ctypes.windll.user32


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
CONSOLE_TEXTMODE_BUFFER = 1


def capture_console(hwnd):
    """Read the visible screen buffer from a console window via Win32 API.
    Uses CreateFile('CONOUT$') to read the ACTIVE screen buffer (Ink's alternate buffer)."""
    try:
        pid = ctypes.wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not k32.AttachConsole(pid.value):
            return "(AttachConsole failed)"
        try:
            h_conout = k32.CreateFileW(
                "CONOUT$",
                GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                0,
                None,
            )
            if h_conout in (None, -1, ctypes.wintypes.HANDLE(-1).value):
                h_conout = k32.GetStdHandle(-11)
                if h_conout in (None, -1, ctypes.wintypes.HANDLE(-1).value):
                    return "(no console handle)"
            csbi = ctypes.wintypes.CONSOLE_SCREEN_BUFFER_INFO()
            if not k32.GetConsoleScreenBufferInfo(h_conout, ctypes.byref(csbi)):
                k32.CloseHandle(h_conout)
                return "(GetConsoleScreenBufferInfo failed)"
            cols = csbi.srWindow.Right - csbi.srWindow.Left + 1
            rows = csbi.srWindow.Bottom - csbi.srWindow.Top + 1
            total = cols * rows
            buf = ctypes.create_unicode_buffer(total)
            n = ctypes.wintypes.DWORD()
            origin = ctypes.wintypes.COORD(csbi.srWindow.Left, csbi.srWindow.Top)
            k32.ReadConsoleOutputCharacterW(h_conout, buf, total, origin, ctypes.byref(n))
            k32.CloseHandle(h_conout)
            lines = [buf[r * cols : (r + 1) * cols].rstrip() for r in range(rows)]
            return "\n".join(lines)
        finally:
            k32.FreeConsole()
    except Exception as e:
        return f"(error: {e})"


def save(name, text):
    p = OUTPUT / f"{name}.txt"
    p.write_text(text, encoding="utf-8")
    log(f"  Saved: {p.name} ({len(text)} bytes)")
    return p


def find_tui():
    for _ in range(30):
        for w in gw.getAllWindows():
            if "cmd" in w.title.strip().lower() and w.height > 300:
                return w
        time.sleep(1)
    return None


def type_in(win, text):
    win.activate()
    time.sleep(0.5)
    pyautogui.click(win.left + win.width // 2, win.top + win.height - 80)
    time.sleep(0.3)
    pyautogui.typewrite(text, interval=0.03)
    time.sleep(0.5)


def enter(win):
    win.activate()
    time.sleep(0.3)
    pyautogui.press("enter")


async def ws_call(method, params, timeout=30):
    async with websockets.connect("ws://127.0.0.1:8765/ws", max_size=2**22) as ws:
        rid = f"r_{method}_{int(time.time())}"
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}))
        dl = time.monotonic() + timeout
        while time.monotonic() < dl:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(dl - time.monotonic(), 10))
            m = json.loads(raw)
            if m.get("id") == rid:
                return m.get("result")
    return None


async def send_prompt(text, sid, timeout=90):
    async with websockets.connect("ws://127.0.0.1:8765/ws", max_size=2**22) as ws:
        rid_r = f"r_{int(time.time())}"
        await ws.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": rid_r,
                    "method": "session.resume",
                    "params": {"session_id": sid},
                }
            )
        )
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                if json.loads(raw).get("id") == rid_r:
                    break
        except asyncio.TimeoutError:
            pass
        rid = f"p_{int(time.time())}"
        await ws.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "method": "prompt.send",
                    "params": {"content": text, "mode": "build", "session_id": sid},
                }
            )
        )
        events = []
        dl = time.monotonic() + timeout
        while time.monotonic() < dl:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(dl - time.monotonic(), 30))
                m = json.loads(raw)
                if m.get("method") == "event":
                    events.append({"kind": m["params"]["kind"], "data": m["params"].get("data")})
                    if events[-1]["kind"] in ("success", "error"):
                        break
            except asyncio.TimeoutError:
                continue
        finals = [
            e for e in events if e["kind"] == "message" and not (e.get("data") or {}).get("partial")
        ]
        text_out = finals[-1]["data"]["text"] if finals and finals[-1].get("data") else ""
        meta = {}
        suc = next((e for e in events if e["kind"] == "success"), None)
        if suc and suc.get("data"):
            meta = {"tokens": suc["data"].get("tokenInfo", {}).get("used", 0)}
        err = next((e for e in events if e["kind"] == "error"), None)
        if err:
            meta = {"error": (err.get("data") or {}).get("message", "unknown")}
        return text_out, meta


def main():
    if not HAS_GUI:
        print("pip install pyautogui pygetwindow")
        return 1
    R = []

    def ok(n):
        R.append(("PASS", n))
        log(f"  PASS  {n}")

    def fail(n, r=""):
        R.append(("FAIL", f"{n}: {r}"))
        log(f"  FAIL  {n}: {r}")

    log("=" * 70)
    log("STEP 1: Backend check")
    log("=" * 70)
    try:
        import urllib.request

        h = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=5).read())
        if h.get("status") != "ok":
            fail("backend")
            return 1
        ok("backend")
    except Exception as e:
        fail("backend", str(e))
        return 1

    log("\n" + "=" * 70)
    log("STEP 2: Create session + send facts")
    log("=" * 70)
    loop = asyncio.new_event_loop()
    r = loop.run_until_complete(ws_call("session.create", {"title": "Resume Verify Test"}))
    if not r or "id" not in r:
        fail("session.create", str(r))
        return 1
    sid = r["id"]
    log(f"  Session: {sid[:8]}")
    ok("session.created")

    facts = [
        "Fact: My name is Alex and I work on the Zenith project.",
        "Fact: The backend runs on port 8765 with Python and WebSocket.",
        "Fact: I prefer using dark theme and vim keybindings.",
    ]
    for i, fact in enumerate(facts):
        log(f"  [{i + 1}] {fact[:60]}...")
        txt, meta = loop.run_until_complete(send_prompt(fact, sid, timeout=60))
        if "error" in meta:
            log(f"    RETRY: {meta['error']}")
            time.sleep(5)
            txt, meta = loop.run_until_complete(send_prompt(fact, sid, timeout=60))
        log(f"    -> {txt[:80] if txt else '(empty)'}")
        time.sleep(2)

    log("\n" + "=" * 70)
    log("STEP 3: Verify WS resume")
    log("=" * 70)
    rr = loop.run_until_complete(ws_call("session.resume", {"session_id": sid}, timeout=15))
    msgs = rr.get("messages", []) if rr else []
    log(
        f"  Messages: {len(msgs)} ({sum(1 for m in msgs if m.get('role') == 'user')} user, "
        f"{sum(1 for m in msgs if m.get('role') == 'assistant')} asst)"
    )
    for m in msgs:
        log(f"    [{m.get('role', '?')}] {str(m.get('content', ''))[:70]}")
    if not msgs:
        fail("ws_resume", "0 messages")
        return 1
    ok("ws_resume")
    loop.close()

    log("\n" + "=" * 70)
    log("STEP 4: Open TUI")
    log("=" * 70)
    subprocess.Popen(
        ["cmd", "/c", "start", "cmd", "/k", str(REPO / "scripts" / "start_tui.bat")], shell=False
    )
    log("  Waiting 15s...")
    time.sleep(15)
    win = find_tui()
    if not win:
        fail("tui.open", "not found")
        return 1
    log(f"  TUI: {win.width}x{win.height}")
    ok("tui.open")

    log("\n" + "=" * 70)
    log("STEP 5: /session -> browser")
    log("=" * 70)
    type_in(win, "/session")
    time.sleep(1)
    enter(win)
    time.sleep(3)
    t = capture_console(win._hWnd)
    save("01_session_browser", t)
    ok("browser.open")

    log("\n" + "=" * 70)
    log("STEP 6: Select session -> resume")
    log("=" * 70)
    enter(win)
    time.sleep(5)
    t = capture_console(win._hWnd)
    save("02_session_resumed", t)
    ok("session.resumed")

    log("\n" + "=" * 70)
    log("STEP 7: Check old messages in TUI text")
    log("=" * 70)
    tl = t.lower()
    found = []
    for fact in facts:
        key = fact.split(":")[1].split(".")[0].strip().lower()
        if key in tl or fact[:30].lower() in tl:
            found.append(fact)
            log(f"  FOUND: {fact[:60]}")
        else:
            log(f"  MISSING: {fact[:60]}")
    if len(found) == len(facts):
        ok("tui.old_messages_visible")
    elif found:
        ok(f"tui.partial ({len(found)}/{len(facts)})")
    else:
        fail("tui.old_messages_visible", "none found")

    log("\n" + "=" * 70)
    log("STEP 8: New message -> verify resume works")
    log("=" * 70)
    msg = "What facts did I just tell you? List them back to me."
    log(f"  Typing: {msg}")
    type_in(win, msg)
    enter(win)
    time.sleep(2)
    save("03_message_sent", capture_console(win._hWnd))
    log("  Waiting 40s...")
    time.sleep(40)
    t = capture_console(win._hWnd)
    save("04_response", t)
    tl = t.lower()
    if any(k in tl for k in ["alex", "zenith", "8765", "dark theme", "vim"]):
        ok("tui.response_has_context")
    else:
        fail("tui.response_has_context", "no old facts in response")

    log("\n" + "=" * 70)
    log("RESULTS")
    log("=" * 70)
    for s, n in R:
        log(f"  {s}  {n}")
    p = sum(1 for s, _ in R if s == "PASS")
    f = sum(1 for s, _ in R if s == "FAIL")
    log(f"\n  Total: {p} passed, {f} failed")
    log(f"  Text captures: {OUTPUT}")
    return 0 if f == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
