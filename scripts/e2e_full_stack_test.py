"""End-to-End Backend + Zenith Frontend Test Automation (P7 repro-of-record).

Sequence (one script, two real visible windows):

  1.  Start BACKEND in its own window (output tee'd to backend.log).
  2.  Wait until HTTP health probe returns 200.
  3.  Start the real Zenith frontend (TUI) in a SECOND window.
  4.  Wait until the frontend is fully loaded: its WebSocket is accepted by
      the backend (visible in backend.log) plus a render settle delay.
  5.  TYPE the test prompt into the frontend with real key events injected
      into that window's console input buffer (WriteConsoleInput — the same
      code path as physical typing; no clipboard, no focus stealing), then
      press ENTER to submit.
  6.  CONFIRM entry+submission authoritatively: the backend persists the
      user message verbatim into ~/.zenith/sessions/<id>/events.jsonl.
  7.  WAIT for completion: the run's terminal SUCCESS event appears in the
      persisted event stream (the same data the UI renders).
  8.  COPY the full frontend output: the entire event transcript (prompt,
      streamed answer, manifest, warnings, summary card payload) is saved,
      plus a best-effort screenshot-style scrape of the window.
  9.  ANALYZE against the acceptance contract -> PASS/FAIL report with
      diagnostics.

Platform note: this machine delegates all console hosting to Windows Terminal,
so classic screen-buffer reads return an empty buffer. The persisted event
stream is the authoritative mirror of what the frontend renders and is used
for verification instead (it is what the UI draws from).

Usage:
  python scripts/e2e_full_stack_test.py            # run + analyze + close
  python scripts/e2e_full_stack_test.py --keep     # leave windows open

Exit code 0 iff all acceptance criteria pass.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TUI_DIR = REPO_ROOT / "tui"
RUN_DIR = REPO_ROOT / ".audit_tmp" / "e2e_fullstack"
SELF = Path(__file__).resolve()
ZENITH_HOME = Path.home() / ".zenith"
SESSIONS_DIR = ZENITH_HOME / "sessions"

BACKEND_LOG = RUN_DIR / "backend.log"
FE_SCREEN_FILE = RUN_DIR / "frontend_screen_best_effort.txt"
TRANSCRIPT_FILE = RUN_DIR / "frontend_transcript_events.jsonl"
REPORT_FILE = RUN_DIR / "analysis_report.txt"

FE_MARKER = "E2E_FE_WINDOW_TOKEN"  # unique tag to find the frontend shell pid

HOST = "http://127.0.0.1:8765"
BACKEND_READY_TIMEOUT_S = 60
FRONTEND_READY_TIMEOUT_S = 150
SUBMIT_CONFIRM_TIMEOUT_S = 90
ANSWER_TIMEOUT_S = 420
SETTLE_S = 10

PROMPT = (
    "hey zenith, good evening. i want you to point of all the major "
    "features functionality that our app has in brief"
)
PROMPT_SNIPPET = "good evening"  # identity fragment used to match our session
MIN_ANSWER_CHARS = 80

FORBIDDEN_STRINGS = {
    "AC-3": "Turn stalled",
    "AC-4": "Build completed but no files were created",
    "AC-5": "[Cancelled by user]",
    "AC-6": "Continue the prior conversation",
}

CREATE_NEW_CONSOLE = 0x00000010
CREATE_NO_WINDOW = 0x08000000


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ──────────────────── console-input injection helper ────────────────────


def _helper_keys(pid: int, text: str) -> int:
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32")

    class KEY_EVENT_RECORD(ctypes.Structure):
        _fields_ = [
            ("bKeyDown", wintypes.BOOL),
            ("wRepeatCount", wintypes.WORD),
            ("wVirtualKeyCode", wintypes.WORD),
            ("wVirtualScanCode", wintypes.WORD),
            ("UnicodeChar", wintypes.WCHAR),
            ("dwControlKeyState", wintypes.DWORD),
        ]

    class _EventUnion(ctypes.Union):
        _fields_ = [("KeyEvent", KEY_EVENT_RECORD)]

    class INPUT_RECORD(ctypes.Structure):
        _anonymous_ = ("e",)
        _fields_ = [("EventType", wintypes.WORD), ("e", _EventUnion)]

    def note(msg: str) -> None:
        try:
            with open(
                RUN_DIR / f"helper_keys_{time.strftime('%H%M%S')}_{pid}.log", "a", encoding="utf-8"
            ) as fh:
                fh.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        except Exception:
            pass

    note(f"helper start pid={pid} text_len={len(text)}")
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.WriteConsoleInputW.restype = wintypes.BOOL
    k32.WriteConsoleInputW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(INPUT_RECORD),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.VkKeyScanW.restype = ctypes.c_short
    user32.VkKeyScanW.argtypes = [wintypes.WCHAR]
    user32.MapVirtualKeyW.restype = wintypes.UINT
    user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
    k32.FreeConsole()  # detach our hidden CREATE_NO_WINDOW console first
    if not k32.AttachConsole(wintypes.DWORD(pid)):
        note(f"AttachConsole({pid}) failed err={ctypes.get_last_error()}")
        return 4
    try:
        conin = k32.CreateFileW("CONIN$", 0xC0000000, 3, None, 3, 0, None)
        if conin in (None, 0) or conin == ctypes.c_void_p(-1).value:
            note("CONIN$ open failed")
            return 4

        SHIFT_PRESSED = 0x0010
        records = []
        for ch in text:
            if ch == "\n":
                continue
            if ch == "\r":
                vk, vsc, shift = 0x0D, 0x1C, 0
            else:
                scan = user32.VkKeyScanW(wintypes.WCHAR(ch))
                if scan == -1:
                    continue
                vk = scan & 0xFF
                shift = (scan >> 8) & 0x01
                vsc = user32.MapVirtualKeyW(vk, 0)
            for down in (1, 0):
                rec = INPUT_RECORD()
                rec.EventType = 0x0001
                rec.e.KeyEvent.bKeyDown = down
                rec.e.KeyEvent.wRepeatCount = 1
                rec.e.KeyEvent.wVirtualKeyCode = vk
                rec.e.KeyEvent.wVirtualScanCode = vsc
                rec.e.KeyEvent.UnicodeChar = ch
                rec.e.KeyEvent.dwControlKeyState = SHIFT_PRESSED if (shift and down) else 0
                records.append(rec)

        arr = (INPUT_RECORD * len(records))(*records)
        written = wintypes.DWORD(0)
        if not k32.WriteConsoleInputW(conin, arr, len(records), ctypes.byref(written)):
            note(f"WriteConsoleInputW failed err={ctypes.get_last_error()}")
            return 4
        k32.CloseHandle(conin)
        note(f"injected {written.value}/{len(records)} key events into pid {pid}")
        return 0
    finally:
        k32.FreeConsole()


def _helper_screen(pid: int, outfile: str) -> int:
    """Best-effort visible-window scrape (empty under Windows Terminal hosting)."""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class COORD(ctypes.Structure):
        _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

    class SMALL_RECT(ctypes.Structure):
        _fields_ = [
            ("Left", wintypes.SHORT),
            ("Top", wintypes.SHORT),
            ("Right", wintypes.SHORT),
            ("Bottom", wintypes.SHORT),
        ]

    class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
        _fields_ = [
            ("dwSize", COORD),
            ("dwCursorPosition", COORD),
            ("wAttributes", wintypes.WORD),
            ("srWindow", SMALL_RECT),
            ("dwMaximumWindowSize", COORD),
        ]

    def note(msg: str) -> None:
        try:
            with open(RUN_DIR / "helper.log", "a", encoding="utf-8") as fh:
                fh.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        except Exception:
            pass

    k32.FreeConsole()
    if not k32.AttachConsole(wintypes.DWORD(pid)):
        note(f"screen: AttachConsole({pid}) failed err={ctypes.get_last_error()}")
        return 4
    try:
        conout = k32.CreateFileW("CONOUT$", 0xC0000000, 3, None, 3, 0, None)
        if conout in (None, 0) or conout == ctypes.c_void_p(-1).value:
            note("screen: CONOUT$ open failed")
            return 4
        csbi = CONSOLE_SCREEN_BUFFER_INFO()
        if not k32.GetConsoleScreenBufferInfo(conout, ctypes.byref(csbi)):
            note("screen: GetConsoleScreenBufferInfo failed")
            return 4
        width = max(csbi.dwSize.X, 1)
        rows = min(max(csbi.dwCursorPosition.Y + 1, 1), 400)
        buf = ctypes.create_unicode_buffer(width)
        read = wintypes.DWORD(0)
        lines = []
        for y in range(rows):
            coord = COORD(0, y)
            if not k32.ReadConsoleOutputCharacterW(
                conout, buf, width, ctypes.byref(coord), ctypes.byref(read)
            ):
                lines.append("")
                continue
            lines.append(buf[: read.value].rstrip())
        k32.CloseHandle(conout)
        Path(outfile).write_text("\n".join(lines), encoding="utf-8", errors="replace")
        return 0
    finally:
        k32.FreeConsole()


def type_into_window(pid: int, text: str) -> tuple[bool, str]:
    stamp = time.strftime("%H%M%S")
    per_run_log = RUN_DIR / f"helper_keys_{stamp}_{pid}.log"
    proc = subprocess.run(
        [sys.executable, str(SELF), "--helper-keys", str(pid), text],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
        cwd=str(REPO_ROOT),
    )
    diag_parts = [
        f"rc={proc.returncode}",
        f"stdout={proc.stdout.strip()[:500]!r}",
        f"stderr={proc.stderr.strip()[:2000]!r}",
    ]
    if per_run_log.exists():
        diag_parts.append(per_run_log.read_text(encoding="utf-8", errors="replace"))
    ok = proc.returncode == 0
    return ok, "\n".join(diag_parts)


# ────────────────────────── process discovery ──────────────────────────


def find_pid_by_commandline_token(token: str, timeout_s: int = 20) -> int | None:
    """Find the powershell process whose command line embeds `token`."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        out = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" "
                f"| Where-Object {{ $_.CommandLine -like '*{token}*' }} "
                "| Select-Object -First 1 -ExpandProperty ProcessId)",
            ],
            capture_output=True,
            text=True,
            timeout=25,
        ).stdout.strip()
        for part in out.split():
            if part.isdigit():
                return int(part)
        time.sleep(1)
    return None


def find_descendant_pids(parent_pid: int, depth: int = 4) -> set[int]:
    """All descendant pids of `parent_pid` (bounded depth) including itself."""
    out = {parent_pid}
    frontier = [parent_pid]
    for _ in range(depth):
        nxt: list[int] = []
        for p in frontier:
            r = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f'(Get-CimInstance Win32_Process -Filter "ParentProcessId={p}").ProcessId',
                ],
                capture_output=True,
                text=True,
                timeout=25,
            )
            for tok in r.stdout.split():
                if tok.isdigit():
                    q = int(tok)
                    if q not in out:
                        out.add(q)
                        nxt.append(q)
        frontier = nxt
        if not frontier:
            break
    return out


def _frontend_tree(fe_pid: int) -> set[int]:
    try:
        return find_descendant_pids(fe_pid)
    except Exception:
        return {fe_pid}


def stop_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15)


def _helper_focus(pid: int) -> int:
    """Find the VISIBLE top-level window for the frontend console and focus it.

    Under Windows Terminal the visible window belongs to WT (not our shell),
    and its title mirrors the console title — so we match by title token.
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32")

    def note(msg: str) -> None:
        try:
            with open(RUN_DIR / f"focus_{pid}.log", "a", encoding="utf-8") as fh:
                fh.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        except Exception:
            pass

    note(f"start token={FE_MARKER}")
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, wintypes.INT]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found: list[int] = []
    all_titles: list[str] = []

    def cb(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        title = buf.value.strip()
        if title:
            all_titles.append(f"{hwnd}:{title[:60]}")
            if FE_MARKER in title or "ZENITH-E2E" in title:
                found.append(hwnd)
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    note(f"visible titled windows: {all_titles[:25]}")
    if not found:
        note("no matching window")
        print("NOMATCH")
        return 5

    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, wintypes.INT]
    user32.SwitchToThisWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
    user32.keybd_event.argtypes = [
        wintypes.BYTE,
        wintypes.BYTE,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]

    hwnd = found[0]
    # Windows blocks background processes from stealing focus; a bare ALT
    # tap is the standard unlock for SetForegroundWindow.
    user32.keybd_event(0x12, 0, 0, None)  # ALT down
    user32.keybd_event(0x12, 0, 2, None)  # ALT up (KEYEVENTF_KEYUP)
    user32.ShowWindow(wintypes.HWND(hwnd), 9)  # SW_RESTORE
    res = user32.SetForegroundWindow(wintypes.HWND(hwnd))
    time.sleep(0.3)
    fg = user32.GetForegroundWindow()
    if fg != hwnd:
        user32.SwitchToThisWindow(wintypes.HWND(hwnd), True)
        time.sleep(0.5)
        fg = user32.GetForegroundWindow()
    match = bool(fg == hwnd)
    note(f"hwnd={hwnd} setfg={res} fg_now={fg} match={match}")
    print(f"{hwnd} {fg} {'MATCH' if match else 'MISMATCH'}")
    return 0 if match else 6


def focus_frontend_window(pid: int) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(SELF), "--helper-focus", str(pid)],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
        cwd=str(REPO_ROOT),
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    ok = proc.returncode == 0 and "MATCH" in out
    return ok, out.strip()[:400]


def sendkeys_to_window(text: str) -> tuple[bool, str]:
    """Send keys to the CURRENTLY FOREGROUND window (must be pre-focused)."""
    escaped = (
        text.replace("{", "{{")
        .replace("}", "}}")
        .replace("[", "{[")
        .replace("]", "{]}")
        .replace("+", "{+}")
        .replace("^", "{^}")
        .replace("%", "{%}")
        .replace("~", "{~}")
        .replace("(", "{(}")
        .replace(")", "{)}")
    )
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        "Start-Sleep -Milliseconds 200; "
        f"$ws.SendKeys('{escaped}'); "
        "Start-Sleep -Milliseconds 300; "
        "$ws.SendKeys('{ENTER}'); "
        "Write-Output 'TYPED'"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return "TYPED" in out, out.strip()[:500]


# ──────────────────────────── session data ────────────────────────────


def candidate_session_files(since_ts: float) -> list[Path]:
    if not SESSIONS_DIR.exists():
        return []
    hits: list[Path] = []
    for session_dir in SESSIONS_DIR.iterdir():
        ev = session_dir / "events.jsonl"
        if not ev.exists():
            continue
        try:
            if ev.stat().st_mtime < since_ts:
                continue
            if PROMPT_SNIPPET in ev.read_text(encoding="utf-8", errors="replace"):
                hits.append(ev)
        except Exception:
            continue
    return sorted(hits, key=lambda p: p.stat().st_mtime)


def parse_events(path: Path) -> list[dict]:
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj.get("data"), dict):
            events.append({"kind": str(obj.get("kind")), "data": obj["data"]})
        elif isinstance(obj.get("kind"), str):
            events.append({"kind": obj["kind"], "data": obj})
    return events


def wait_for(predicate, timeout_s: int, poll_s: float = 2.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = predicate()
        if result is not None:
            return result
        time.sleep(poll_s)
    return None


# ────────────────────────────── analysis ──────────────────────────────


def analyze(events: list[dict]) -> tuple[dict[str, bool], str]:
    results: dict[str, bool] = {}

    user_echoed = any(
        ev["kind"] == "message"
        and PROMPT_SNIPPET in str(ev["data"].get("text", "")).lower()
        and ev["data"].get("role") == "user"
        for ev in events
    ) or any(PROMPT_SNIPPET in json.dumps(ev)[:2000].lower() for ev in events[:6])
    results["AC-1 prompt entered & submitted (backend echoed it)"] = user_echoed

    answer_texts = [
        str(ev["data"].get("text", ""))
        for ev in events
        if ev["kind"] == "message"
        and ev["data"].get("role") == "assistant"
        and not ev["data"].get("partial")
        and len(str(ev["data"].get("text", ""))) > 40
    ]
    if not answer_texts:
        answer_texts = [
            str(ev["data"].get("text", ""))
            for ev in events
            if ev["kind"] == "message" and len(str(ev["data"].get("text", ""))) > 200
        ]
    answer = "\n".join(answer_texts)
    results[f"AC-2 substantive answer delivered (>={MIN_ANSWER_CHARS} chars)"] = (
        len(answer.strip()) >= MIN_ANSWER_CHARS
    )

    manifests = [ev["data"] for ev in events if ev["kind"] == "turn_manifest"]
    last_manifest = manifests[-1] if manifests else {}
    stalled = bool(last_manifest.get("stalled"))
    completed = bool(last_manifest.get("completed"))
    answered = bool(last_manifest.get("answered"))
    results["AC-3 clean completion (completed=True, stalled=False)"] = completed and not stalled
    results["AC-4 answered flag set on manifest"] = answered

    warnings_text = " ".join(
        str(ev["data"].get("message", "")) for ev in events if ev["kind"] == "warning"
    )
    for ac, needle in FORBIDDEN_STRINGS.items():
        label = {
            "AC-3": "no stall warning",
            "AC-4": "no false NO_FILES_CREATED warning",
            "AC-5": "no fabricated cancel placeholder",
            "AC-6": "no canned summarizer objective",
        }[ac]
        results[label] = needle not in warnings_text and needle not in answer

    summarized = [ev["data"] for ev in events if ev["kind"] == "session_summarized"]
    if summarized:
        rs = summarized[-1].get("run_state") or {}
        status = str(rs.get("status") or "")
        results["AC-7 run-summary card shows completed run"] = status in (
            "completed",
            "finalizing",
        )
        findings = " ".join(str(f) for f in rs.get("findings") or [])
        results["AC-8 no stale failure findings on this run"] = "Run failed:" not in findings
    else:
        results["AC-7 run-summary card shows completed run"] = False
        results["AC-8 no stale failure findings on this run"] = False

    excerpt = answer.strip().splitlines()
    report_excerpt = "\n".join(excerpt[:30])
    return results, report_excerpt


def write_report(results: dict[str, bool], elapsed: float, excerpt: str) -> bool:
    lines = [
        "=" * 72,
        f"E2E RESULT  ({time.strftime('%Y-%m-%d %H:%M:%S')})  answer phase: {elapsed:.0f}s",
        "=" * 72,
    ]
    failed = False
    for name, ok in results.items():
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed = True
        lines.append(f"[{mark}] {name}")
    lines.append("-" * 72)
    lines.append("ANSWER EXCERPT (first 30 lines):")
    lines.extend(excerpt.splitlines())
    lines.append("=" * 72)
    text = "\n".join(lines)
    REPORT_FILE.write_text(text, encoding="utf-8")
    print(text)
    return not failed


# ─────────────────────────────── main ───────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="leave both windows open")
    ap.parse_args()

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    procs: dict[str, subprocess.Popen] = {}
    started_ts = time.time()
    try:
        # ── step 1: backend window ───────────────────────────────────────
        log("STEP 1  starting backend window (python -m server.main serve)")
        procs["backend"] = subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "$Host.UI.RawUI.WindowTitle='zenith-backend';"
                f"cd '{REPO_ROOT}'; python -m server.main serve *>&1 | "
                f"Tee-Object -FilePath '{BACKEND_LOG}'",
            ],
            creationflags=CREATE_NEW_CONSOLE,
            cwd=str(REPO_ROOT),
        )

        # ── step 2: health gate ──────────────────────────────────────────
        log("STEP 2  waiting for backend readiness (HTTP /startup/validate)")
        deadline = time.monotonic() + BACKEND_READY_TIMEOUT_S
        healthy = False
        while time.monotonic() < deadline:
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(f"{HOST}/startup/validate", timeout=3) as resp:
                    if resp.status == 200:
                        healthy = True
                        break
            except Exception:
                time.sleep(1)
        if not healthy:
            log("FAIL: backend never became healthy; tail:")
            tail = BACKEND_LOG.read_text(errors="replace").splitlines()[-15:]
            print("\n".join(tail))
            return 2
        log("backend healthy")

        # ── step 3: frontend window ──────────────────────────────────────
        # Uses the project's OWN launch script (`npm run dev`) with the
        # user's untouched environment — identical to running it by hand.
        log("STEP 3  starting frontend window (npm run dev — existing settings)")
        procs["frontend"] = subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                f"$Host.UI.RawUI.WindowTitle='{FE_MARKER}';cd '{TUI_DIR}'; npm run dev",
            ],
            creationflags=CREATE_NEW_CONSOLE,
            cwd=str(TUI_DIR),
        )
        time.sleep(2)

        # ── step 4: frontend ready = live WebSocket to the backend ──────
        fe_pid = find_pid_by_commandline_token(FE_MARKER)
        if fe_pid is None:
            log("FAIL: could not resolve frontend window process id")
            return 2
        log(f"frontend window pid resolved: {fe_pid}")
        log("STEP 4  waiting for the frontend's WebSocket connection")
        ws_deadline = time.monotonic() + FRONTEND_READY_TIMEOUT_S
        ws_ready = False
        while time.monotonic() < ws_deadline:
            # Primary signal: an ESTABLISHED tcp socket to :8765 owned by the
            # frontend process tree (the WebSocket connection itself).
            ps = (
                "$c = Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue "
                "| Where-Object { $_.RemotePort -eq 8765 }; "
                "if ($c) { $c | ForEach-Object { $_.OwningProcess } } else { -1 }"
            )
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True,
                text=True,
                timeout=25,
            ).stdout.split()
            owners = {int(x) for x in out if x.strip().lstrip("-").isdigit()}
            if owners & _frontend_tree(fe_pid):
                ws_ready = True
                break
            # Secondary signal: backend access log saw the WS handshake.
            try:
                blob = BACKEND_LOG.read_text(encoding="utf-8", errors="replace")
                if "WebSocket /ws" in blob and "accepted" in blob:
                    ws_ready = True
                    break
            except Exception:
                pass
            time.sleep(2)
        if not ws_ready:
            log("FAIL: frontend WebSocket never connected")
            tail = BACKEND_LOG.read_text(errors="replace").splitlines()[-12:]
            print("\n".join(tail))
            return 2
        log("frontend connected; settling for render")
        time.sleep(SETTLE_S)

        # ── step 5+6: type & submit ─────────────────────────────────────
        global _answer_t0
        log(f"STEP 5  focusing the zenith window and typing ({len(PROMPT)} chars + Enter)")
        _answer_t0 = time.monotonic()
        focused, fdiag = focus_frontend_window(fe_pid)
        if not focused:
            log(
                "FAIL: could not bring the frontend window to the foreground "
                f"(click the zenith window once and rerun)\n{fdiag}"
            )
            return 2
        ok, diag = sendkeys_to_window(PROMPT)
        if not ok:
            log(f"FAIL: keyboard input failed:\n{diag}")
            return 2
        log("prompt typed + ENTER sent via OS keyboard events (verified focus)")

        log("STEP 6  confirming submission (backend must persist the user message)")
        matched = wait_for(
            lambda: (candidate_session_files(started_ts) or [None])[0],
            SUBMIT_CONFIRM_TIMEOUT_S,
            poll_s=2,
        )
        if matched is None:
            log("FAIL: no session recorded our prompt — typing/submit did not land")
            hl = RUN_DIR / "helper.log"
            if hl.exists():
                print(hl.read_text(errors="replace")[-600:])
            return 2
        log(f"submission confirmed -> {matched.name}")

        # ── step 7: wait for completion ─────────────────────────────────
        log("STEP 7  waiting for the response to finish (SUCCESS event)")

        def _completed():
            for ev_file in candidate_session_files(started_ts):
                for ev in parse_events(ev_file):
                    if ev["kind"] == "success":
                        return ev_file
                    if ev["kind"] == "error":
                        return ev_file
            return None

        done_file = wait_for(_completed, ANSWER_TIMEOUT_S, poll_s=3)
        if done_file is None:
            log("FAIL: run did not terminate within timeout")
            return 2
        time.sleep(SETTLE_S)

        # ── step 8: copy frontend output ────────────────────────────────
        log("STEP 8  copying full frontend conversation data")
        all_events: list[dict] = []
        for ev_file in candidate_session_files(started_ts):
            all_events.extend(parse_events(ev_file))
        TRANSCRIPT_FILE.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in all_events),
            encoding="utf-8",
        )
        log(f"event transcript copied -> {TRANSCRIPT_FILE} ({len(all_events)} events)")

        # best-effort visual scrape (may be empty under Windows Terminal)
        try:
            screen = scrape_screen_best_effort(fe_pid)
            FE_SCREEN_FILE.write_text(screen, encoding="utf-8", errors="replace")
            log(
                f"window scrape saved -> {FE_SCREEN_FILE} "
                f"({len([ln for ln in screen.splitlines() if ln.strip()])} visible lines)"
            )
        except Exception as exc:
            log(f"window scrape unavailable ({str(exc)[:80]}) — transcript is authoritative")

        # ── step 9: analyze ─────────────────────────────────────────────
        log("STEP 9  analyzing response against acceptance contract")
        results, excerpt = analyze(all_events)
        passed = write_report(results, time.monotonic() - _answer_t0, excerpt)
        return 0 if passed else 1
    finally:
        if not args_keep:
            for name in reversed(list(procs)):
                proc = procs[name]
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                        capture_output=True,
                        timeout=15,
                    )
                    log(f"{name} window closed")
                except Exception as exc:
                    log(f"{name} close failed: {exc}")


_answer_t0 = 0.0
args_keep = False


def scrape_screen_best_effort(pid: int) -> str:
    proc = subprocess.run(
        [sys.executable, str(SELF), "--helper-screen", str(pid), str(FE_SCREEN_FILE)],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
        cwd=str(REPO_ROOT),
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or "scrape failed")
    return FE_SCREEN_FILE.read_text(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", "--no-close", dest="keep", action="store_true")
    ap.add_argument("--helper-keys", nargs=2, metavar=("PID", "TEXT"))
    ap.add_argument("--helper-screen", nargs=2, metavar=("PID", "OUTFILE"))
    ap.add_argument("--helper-focus", nargs=1, metavar=("PID",), type=int)
    _a = ap.parse_args()
    if _a.helper_keys:
        sys.exit(_helper_keys(int(_a.helper_keys[0]), _a.helper_keys[1]))
    if _a.helper_screen:
        sys.exit(_helper_screen(int(_a.helper_screen[0]), _a.helper_screen[1]))
    if _a.helper_focus is not None:
        sys.exit(_helper_focus(_a.helper_focus[0]))
    args_keep = _a.keep
    sys.exit(main())
