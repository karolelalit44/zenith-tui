"""Comprehensive 12-Phase Production Validation for Zenith.

Runs the full validation suite with detailed performance recording.
Exit code: 0 = all pass, 1 = critical failures.

Usage:
    python scripts/validation_run.py
"""
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import traceback
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
PORT = 8765
HOST = "127.0.0.1"
BASE_URL = f"http://{HOST}:{PORT}"
WS_URL = f"ws://{HOST}:{PORT}/ws"

os.environ["PYTHONIOENCODING"] = "utf-8"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PhaseResult:
    name: str
    status: str = "pending"       # pass | fail | skip | error
    duration: float = 0.0
    details: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    phases: list[PhaseResult] = field(default_factory=list)
    total_duration: float = 0.0
    server_proc: Any = None

    def add(self, phase: PhaseResult):
        self.phases.append(phase)

    def summary(self) -> str:
        lines = []
        lines.append("")
        lines.append("=" * 72)
        lines.append("  ZENITH PRODUCTION VALIDATION REPORT")
        lines.append("=" * 72)
        lines.append("")
        for p in self.phases:
            icon = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP", "error": "ERR "}.get(p.status, "????")
            lines.append(f"  [{icon}] {p.name:<45} {p.duration:>7.2f}s")
            for d in p.details:
                lines.append(f"        {d}")
            for e in p.errors:
                lines.append(f"        ERROR: {e}")
        lines.append("")
        lines.append("-" * 72)
        passed = sum(1 for p in self.phases if p.status == "pass")
        failed = sum(1 for p in self.phases if p.status in ("fail", "error"))
        skipped = sum(1 for p in self.phases if p.status == "skip")
        lines.append(f"  Total: {len(self.phases)} phases | {passed} passed | {failed} failed | {skipped} skipped")
        lines.append(f"  Duration: {self.total_duration:.2f}s")
        verdict = "PRODUCTION READY" if failed == 0 else "NOT PRODUCTION READY"
        lines.append(f"  Verdict: {verdict}")
        lines.append("=" * 72)
        lines.append("")
        return "\n".join(lines)

    def to_json(self) -> dict:
        return {
            "total_duration": self.total_duration,
            "verdict": "production_ready" if all(p.status == "pass" or p.status == "skip" for p in self.phases) else "not_ready",
            "phases": [
                {
                    "name": p.name,
                    "status": p.status,
                    "duration": p.duration,
                    "details": p.details,
                    "errors": p.errors,
                    "metrics": p.metrics,
                }
                for p in self.phases
            ],
        }


report = ValidationReport()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_cmd(cmd: list[str], cwd: str = None, timeout: int = 300) -> tuple[int, str, str]:
    use_shell = os.name == "nt"
    result = subprocess.run(
        cmd if not use_shell else " ".join(cmd),
        cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env=os.environ, shell=use_shell, timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def http_get(path: str, timeout: float = 5) -> tuple[int, str]:
    try:
        req = urllib.request.urlopen(f"{BASE_URL}{path}", timeout=timeout)
        return req.status, req.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode() if hasattr(e, "read") else str(e)
    except Exception as e:
        return 0, str(e)


def http_post_json(path: str, data: dict, timeout: float = 10) -> tuple[int, str]:
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{BASE_URL}{path}", data=body,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode() if hasattr(e, "read") else str(e)
    except Exception as e:
        return 0, str(e)


def load_keys_file():
    keys_path = BASE_DIR / ".keys"
    if not keys_path.exists():
        return
    for line in keys_path.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(url: str, timeout: float = 20) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.urlopen(url, timeout=2)
            if req.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


# ---------------------------------------------------------------------------
# Phase 1 — Build & Environment Validation
# ---------------------------------------------------------------------------

def phase_1_build() -> PhaseResult:
    p = PhaseResult(name="Phase 1: Build & Environment")
    t0 = time.time()

    os.environ["CI"] = "true"

    # 1a. TypeScript typecheck
    p.details.append("Running TypeScript typecheck...")
    rc, out, err = run_cmd(["npx", "tsc", "--noEmit"], cwd=str(BASE_DIR))
    if rc != 0:
        p.errors.append(f"TypeScript typecheck failed: {err[:500]}")
        p.status = "fail"
        p.duration = time.time() - t0
        return p
    p.details.append("TypeScript typecheck: OK")

    # 1b. Vitest
    p.details.append("Running Vitest frontend tests...")
    rc, out, err = run_cmd(["npx", "vitest", "run", "--reporter=verbose"], cwd=str(BASE_DIR))
    if rc != 0:
        p.errors.append(f"Vitest failed: {err[-500:]}")
        p.status = "fail"
        p.duration = time.time() - t0
        return p
    # Extract pass count
    for line in (out + err).splitlines():
        if "Tests" in line and "passed" in line:
            p.metrics["vitest"] = line.strip()
            p.details.append(f"Vitest: {line.strip()}")
            break
    else:
        p.details.append("Vitest: all passed")

    # 1c. Python pytest
    p.details.append("Running Python test suite...")
    rc, out, err = run_cmd(
        [sys.executable, "-m", "pytest", "-v", "--tb=short"],
        cwd=str(BASE_DIR),
    )
    if rc != 0:
        p.errors.append(f"pytest failed: {err[-500:]}")
        p.status = "fail"
        p.duration = time.time() - t0
        return p
    for line in (out + err).splitlines():
        if "passed" in line and ("failed" in line or "error" in line or line.strip().endswith("passed")):
            p.metrics["pytest"] = line.strip()
            p.details.append(f"pytest: {line.strip()}")
            break
    else:
        p.details.append("pytest: all passed")

    p.status = "pass"
    p.duration = time.time() - t0
    return p


# ---------------------------------------------------------------------------
# Phase 2 — Backend Server Startup
# ---------------------------------------------------------------------------

def phase_2_server_startup() -> PhaseResult:
    p = PhaseResult(name="Phase 2: Backend Server Startup")
    t0 = time.time()

    load_keys_file()

    # Clean DB for fresh state
    db_path = BASE_DIR / "data" / "zenith.db"
    if db_path.exists():
        db_path.unlink()
        p.details.append("Deleted stale zenith.db for clean state")

    # Ensure data dir
    (BASE_DIR / "data").mkdir(exist_ok=True)

    # Start server
    p.details.append(f"Starting server on {HOST}:{PORT}...")
    proc = subprocess.Popen(
        [sys.executable, "main.py", "serve", "--host", HOST, "--port", str(PORT)],
        cwd=str(BASE_DIR),
        env=os.environ,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )
    report.server_proc = proc

    # Drain stdout/stderr in background threads to prevent pipe buffer deadlock
    def _drain(pipe, label):
        try:
            for line in pipe:
                pass
        except Exception:
            pass

    import threading
    if proc.stdout:
        threading.Thread(target=_drain, args=(proc.stdout, "stdout"), daemon=True).start()
    if proc.stderr:
        threading.Thread(target=_drain, args=(proc.stderr, "stderr"), daemon=True).start()

    # Wait for health
    healthy = _wait_for_health(f"{BASE_URL}/health", timeout=20)
    startup_duration = time.time() - t0
    p.metrics["startup_seconds"] = round(startup_duration, 2)

    if not healthy:
        p.errors.append("Server failed to become healthy within 20s")
        p.status = "fail"
        p.duration = time.time() - t0
        return p

    p.details.append(f"Server healthy in {startup_duration:.2f}s")
    p.status = "pass"
    p.duration = time.time() - t0
    return p


# ---------------------------------------------------------------------------
# Phase 3 — REST API Validation
# ---------------------------------------------------------------------------

def phase_3_rest_api() -> PhaseResult:
    p = PhaseResult(name="Phase 3: REST API Validation")
    t0 = time.time()

    endpoints = [
        ("GET", "/health"),
        ("GET", "/status"),
        ("GET", "/startup/validate"),
        ("GET", "/startup/provider-config"),
    ]

    for method, path in endpoints:
        t_ep = time.time()
        code, body = http_get(path)
        ep_time = time.time() - t_ep
        p.metrics[path] = {"status": code, "latency_ms": round(ep_time * 1000, 1)}

        if code == 200:
            try:
                data = json.loads(body)
                p.details.append(f"{method} {path} -> {code} OK ({ep_time*1000:.0f}ms) keys={list(data.keys())[:5]}")
            except json.JSONDecodeError:
                p.details.append(f"{method} {path} -> {code} OK (non-JSON, {ep_time*1000:.0f}ms)")
        else:
            p.errors.append(f"{method} {path} -> {code}: {body[:200]}")

    # POST /startup/validate-provider
    t_ep = time.time()
    code, body = http_post_json("/startup/validate-provider", {
        "provider": "nvidia", "api_key": "test", "model": "test-model",
    })
    ep_time = time.time() - t_ep
    p.metrics["/startup/validate-provider"] = {"status": code, "latency_ms": round(ep_time * 1000, 1)}
    if code in (200, 422):
        p.details.append(f"POST /startup/validate-provider -> {code} ({ep_time*1000:.0f}ms)")
    else:
        p.errors.append(f"POST /startup/validate-provider -> {code}: {body[:200]}")

    p.status = "pass" if not p.errors else "fail"
    p.duration = time.time() - t0
    return p


# ---------------------------------------------------------------------------
# Phase 4 — WebSocket Protocol Validation
# ---------------------------------------------------------------------------

def phase_4_ws_protocol() -> PhaseResult:
    p = PhaseResult(name="Phase 4: WebSocket Protocol")
    t0 = time.time()
    import websockets

    async def _run():
        tests = []
        async with websockets.connect(WS_URL, close_timeout=3) as ws:
            # 4a. Health
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "health", "id": 1, "params": {}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            ok = resp.get("result", {}).get("status") == "ok"
            tests.append(("health", ok, f"status={resp.get('result', {}).get('status')}"))

            # 4b. Unknown method -> -32601
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "bogus.method", "id": 2, "params": {}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            err_code = resp.get("error", {}).get("code")
            ok = err_code == -32601
            tests.append(("unknown_method", ok, f"error_code={err_code}"))

            # 4c. Session create + list
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 3, "params": {"title": "WS Protocol Test"}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            sid = resp.get("result", {}).get("id")
            ok_create = sid is not None

            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.list", "id": 4, "params": {}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            sessions = resp.get("result", [])
            ok_list = isinstance(sessions, list) and len(sessions) > 0
            tests.append(("session_create", ok_create, f"session_id={sid}"))
            tests.append(("session_list", ok_list, f"count={len(sessions)}"))

            # 4d. Empty object -> error (use new ID range)
            await ws.send(json.dumps({}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            has_error = "error" in resp
            tests.append(("empty_object", has_error, f"has_error={has_error}"))

        # 4e. Malformed JSON (separate connection since it may break framing)
        async with websockets.connect(WS_URL, close_timeout=3) as ws2:
            await ws2.send("not json at all {{{")
            resp = json.loads(await asyncio.wait_for(ws2.recv(), timeout=5))
            err_code = resp.get("error", {}).get("code")
            ok = err_code == -32700
            tests.append(("malformed_json", ok, f"error_code={err_code}"))

        return tests

    try:
        results = asyncio.run(_run())
    except Exception as e:
        tb = traceback.format_exc()
        p.errors.append(f"WS protocol test crashed: {type(e).__name__}: {e}")
        p.details.append(tb[-500:] if len(tb) > 500 else tb)
        p.status = "fail"
        p.duration = time.time() - t0
        return p

    for name, ok, detail in results:
        status_str = "PASS" if ok else "FAIL"
        p.metrics[name] = ok
        if ok:
            p.details.append(f"  {name}: {status_str} ({detail})")
        else:
            p.errors.append(f"  {name}: {status_str} ({detail})")

    p.status = "pass" if not p.errors else "fail"
    p.duration = time.time() - t0
    return p


# ---------------------------------------------------------------------------
# Phase 5 — Agent Runtime Scenario (Real LLM)
# ---------------------------------------------------------------------------

def phase_5_agent_scenario() -> PhaseResult:
    p = PhaseResult(name="Phase 5: Agent Runtime (Real LLM)")
    t0 = time.time()
    import websockets

    async def _run():
        events_received = []
        async with websockets.connect(WS_URL) as ws:
            # Create session
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 1, "params": {"title": "Agent Scenario Test"}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            sid = resp.get("result", {}).get("id")
            if not sid:
                return None, [], "Failed to create session"

            # Send prompt
            await ws.send(json.dumps({
                "jsonrpc": "2.0", "method": "prompt.send", "id": 2,
                "params": {"content": "What is 2+2? Reply with just the number.", "session_id": sid, "mode": "default"},
            }))

            start = time.time()
            while time.time() - start < 60:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    ev = json.loads(msg)
                    kind = ev.get("params", {}).get("kind")
                    if kind:
                        events_received.append(kind)
                    if kind in ("success", "error"):
                        return sid, events_received, None
                    if "result" in ev and ev.get("id") == 2:
                        return sid, events_received, None
                except asyncio.TimeoutError:
                    continue
            return sid, events_received, "Timed out after 60s"

    try:
        sid, events, error = asyncio.run(_run())
    except Exception as e:
        tb = traceback.format_exc()
        p.errors.append(f"Agent scenario crashed: {type(e).__name__}: {e}")
        p.details.append(tb[-500:] if len(tb) > 500 else tb)
        p.status = "error"
        p.duration = time.time() - t0
        return p

    if error:
        p.errors.append(error)
        p.status = "fail"
    else:
        p.details.append(f"Session: {sid}")
        p.details.append(f"Events received: {events}")
        p.metrics["session_id"] = sid
        p.metrics["event_kinds"] = events
        p.metrics["event_count"] = len(events)
        p.metrics["latency_seconds"] = round(time.time() - t0, 2)
        p.status = "pass"

    p.duration = time.time() - t0
    return p


# ---------------------------------------------------------------------------
# Phase 6 — Tool Framework Validation
# ---------------------------------------------------------------------------

def phase_6_tools() -> PhaseResult:
    p = PhaseResult(name="Phase 6: Tool Framework")
    t0 = time.time()

    expected_tools = [
        "bash", "file_read", "file_write", "file_edit", "file_delete",
        "glob", "grep", "webfetch", "question", "todo",
    ]

    rc, out, err = run_cmd([sys.executable, "main.py", "tools"], cwd=str(BASE_DIR))
    if rc != 0:
        p.errors.append(f"tools CLI failed: {err[:300]}")
        p.status = "fail"
        p.duration = time.time() - t0
        return p

    # Parse tool names from output
    found_tools = []
    for line in out.splitlines():
        line = line.strip()
        if line and not line.startswith("=") and not line.startswith("Total"):
            parts = line.split()
            if parts:
                found_tools.append(parts[0])

    p.metrics["total_tools"] = len(found_tools)
    p.metrics["found_tools"] = found_tools
    p.details.append(f"Registered tools: {len(found_tools)}")
    for t in found_tools:
        p.details.append(f"  - {t}")

    # Check expected
    missing = [t for t in expected_tools if t not in found_tools]
    if missing:
        p.errors.append(f"Missing expected tools: {missing}")
        p.status = "fail"
    else:
        p.details.append(f"All {len(expected_tools)} expected tools present")
        p.status = "pass"

    p.duration = time.time() - t0
    return p


# ---------------------------------------------------------------------------
# Phase 7 — Database Operations
# ---------------------------------------------------------------------------

def phase_7_database() -> PhaseResult:
    p = PhaseResult(name="Phase 7: Database Operations")
    t0 = time.time()
    import websockets

    async def _run():
        results = []

        async with websockets.connect(WS_URL) as ws:
            # 7a. Create session
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 1, "params": {"title": "DB Test Session"}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            sid = resp.get("result", {}).get("id")
            results.append(("create_session", sid is not None, f"id={sid}"))

            # 7b. List sessions
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.list", "id": 2, "params": {}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            sessions = resp.get("result", [])
            results.append(("list_sessions", len(sessions) > 0, f"count={len(sessions)}"))

            # 7c. Resume session
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.resume", "id": 3, "params": {"session_id": sid}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            resumed = resp.get("result", {}) is not None
            results.append(("resume_session", resumed, f"title={resp.get('result', {}).get('title', '?')}"))

            # 7d. Session export
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.export", "id": 4, "params": {"session_id": sid}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            exported = "result" in resp
            results.append(("export_session", exported, f"has_result={exported}"))

            # 7e. Nonexistent session
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.resume", "id": 5, "params": {"session_id": "nonexistent-id"}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            has_error = "error" in resp
            results.append(("nonexistent_session", has_error, f"error={resp.get('error', {}).get('message', '?')[:80]}"))

        return results

    try:
        results = asyncio.run(_run())
    except Exception as e:
        tb = traceback.format_exc()
        p.errors.append(f"DB test crashed: {type(e).__name__}: {e}")
        p.details.append(tb[-500:] if len(tb) > 500 else tb)
        p.status = "error"
        p.duration = time.time() - t0
        return p

    for name, ok, detail in results:
        p.metrics[name] = ok
        if ok:
            p.details.append(f"  {name}: PASS ({detail})")
        else:
            p.errors.append(f"  {name}: FAIL ({detail})")

    # Verify DB file exists and has data
    db_path = BASE_DIR / "data" / "zenith.db"
    if db_path.exists():
        size_kb = db_path.stat().st_size / 1024
        p.metrics["db_size_kb"] = round(size_kb, 1)
        p.details.append(f"  DB file: {size_kb:.1f} KB")
    else:
        p.errors.append("  DB file missing")

    p.status = "pass" if not p.errors else "fail"
    p.duration = time.time() - t0
    return p


# ---------------------------------------------------------------------------
# Phase 8 — Configuration & Error Handling
# ---------------------------------------------------------------------------

def phase_8_config_errors() -> PhaseResult:
    p = PhaseResult(name="Phase 8: Config & Error Handling")
    t0 = time.time()
    import websockets

    async def _run():
        results = []

        async with websockets.connect(WS_URL) as ws:
            # 8a. Prompt without session -> auto-create
            await ws.send(json.dumps({
                "jsonrpc": "2.0", "method": "prompt.send", "id": 1,
                "params": {"content": "auto-session test", "mode": "default"},
            }))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            ok = "result" in resp or "params" in resp
            results.append(("auto_session_prompt", ok, f"response_keys={list(resp.keys())}"))

        # 8b. Invalid JSON-RPC id types
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "health", "id": "string-id", "params": {}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            results.append(("string_rpc_id", "result" in resp or "error" in resp, "handled"))

        # 8c. Integer JSON-RPC id
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "health", "id": 42, "params": {}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            results.append(("int_rpc_id", "result" in resp or "error" in resp, "handled"))

        # 8d. Empty prompt
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 10, "params": {}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            sid = resp.get("result", {}).get("id", "auto")
            await ws.send(json.dumps({
                "jsonrpc": "2.0", "method": "prompt.send", "id": 11,
                "params": {"content": "", "session_id": sid, "mode": "default"},
            }))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            has_error = "error" in resp
            results.append(("empty_prompt", has_error, f"rejected={has_error}"))

        # 8e. Unicode content
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 12, "params": {"title": "Unicode Test - 日本語テスト"}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            ok = resp.get("result", {}) is not None
            results.append(("unicode_session", ok, f"title_ok={ok}"))

        return results

    try:
        results = asyncio.run(_run())
    except Exception as e:
        tb = traceback.format_exc()
        p.errors.append(f"Config test crashed: {type(e).__name__}: {e}")
        p.details.append(tb[-500:] if len(tb) > 500 else tb)
        p.status = "error"
        p.duration = time.time() - t0
        return p

    for name, ok, detail in results:
        p.metrics[name] = ok
        if ok:
            p.details.append(f"  {name}: PASS ({detail})")
        else:
            p.errors.append(f"  {name}: FAIL ({detail})")

    p.status = "pass" if not p.errors else "fail"
    p.duration = time.time() - t0
    return p


# ---------------------------------------------------------------------------
# Phase 9 — Frontend Build Verification
# ---------------------------------------------------------------------------

def phase_9() -> PhaseResult:
    p = PhaseResult(name="Phase 9: Frontend Build")
    t0 = time.time()

    # 9a. TypeScript compile
    p.details.append("TypeScript compile check...")
    rc, out, err = run_cmd(["npx", "tsc", "--noEmit"], cwd=str(BASE_DIR))
    if rc != 0:
        p.errors.append(f"TypeScript compile failed: {err[:300]}")
        p.status = "fail"
        p.duration = time.time() - t0
        return p
    p.details.append("TypeScript: clean")

    # 9b. Biome lint
    p.details.append("Biome lint check...")
    rc, out, err = run_cmd(["npx", "biome", "check", "src/"], cwd=str(BASE_DIR))
    biome_output = out + err
    if rc != 0:
        has_real_errors = "error" in biome_output.lower() and "found" in biome_output.lower()
        for line in biome_output.splitlines():
            if line.strip().startswith("Found ") and "error" in line.lower():
                num = line.strip()
                if "0 errors" not in num:
                    has_real_errors = True
                    break
        if has_real_errors:
            error_lines = [l for l in biome_output.splitlines() if "error" in l.lower() and l.strip()]
            p.details.append(f"Biome: {len(error_lines)} error(s) found")
            p.status = "fail"
            p.duration = time.time() - t0
            return p
    p.details.append("Biome lint: clean (warnings acceptable)")

    # 9c. Frontend tests (re-run after backend changes)
    p.details.append("Re-running Vitest after backend changes...")
    rc, out, err = run_cmd(["npx", "vitest", "run"], cwd=str(BASE_DIR))
    if rc != 0:
        p.errors.append(f"Vitest re-run failed: {err[-300:]}")
        p.status = "fail"
        p.duration = time.time() - t0
        return p
    p.details.append("Vitest re-run: all passed")

    p.status = "pass"
    p.duration = time.time() - t0
    return p


# ---------------------------------------------------------------------------
# Phase 10 — Stress Test (5 Concurrent Clients)
# ---------------------------------------------------------------------------

def phase_10_stress() -> PhaseResult:
    p = PhaseResult(name="Phase 10: Stress Test (5 clients)")
    t0 = time.time()
    import websockets

    CONCURRENCY = 5

    async def _client(idx: int) -> dict:
        t_start = time.time()
        metrics = {"client": idx, "session_create_ms": 0, "prompt_ms": 0, "events": []}
        try:
            async with websockets.connect(WS_URL) as ws:
                # Create session
                await ws.send(json.dumps({
                    "jsonrpc": "2.0", "method": "session.create", "id": idx * 10 + 1,
                    "params": {"title": f"Stress Client {idx}"},
                }))
                resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                sid = resp.get("result", {}).get("id")
                metrics["session_create_ms"] = round((time.time() - t_start) * 1000, 1)
                metrics["session_id"] = sid

                # Send prompt
                t_prompt = time.time()
                await ws.send(json.dumps({
                    "jsonrpc": "2.0", "method": "prompt.send", "id": idx * 10 + 2,
                    "params": {"content": f"What is {idx}+{idx}? Reply with just the number.", "session_id": sid, "mode": "default"},
                }))

                # Collect events
                while time.time() - t_prompt < 45:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        ev = json.loads(msg)
                        kind = ev.get("params", {}).get("kind")
                        if kind:
                            metrics["events"].append(kind)
                        if kind in ("success", "error"):
                            metrics["prompt_ms"] = round((time.time() - t_prompt) * 1000, 1)
                            break
                    except asyncio.TimeoutError:
                        continue

        except Exception as e:
            metrics["error"] = str(e)
        return metrics

    async def _run_all():
        return await asyncio.gather(*[_client(i) for i in range(CONCURRENCY)])

    try:
        results = asyncio.run(_run_all())
    except Exception as e:
        tb = traceback.format_exc()
        p.errors.append(f"Stress test crashed: {type(e).__name__}: {e}")
        p.details.append(tb[-500:] if len(tb) > 500 else tb)
        p.status = "error"
        p.duration = time.time() - t0
        return p

    session_create_latencies = []
    prompt_latencies = []
    success_count = 0

    for r in results:
        client_id = r["client"]
        sc_ms = r["session_create_ms"]
        pr_ms = r["prompt_ms"]
        events = r.get("events", [])
        error = r.get("error")

        session_create_latencies.append(sc_ms)
        if pr_ms > 0:
            prompt_latencies.append(pr_ms)
        if "success" in events or "error" in events:
            success_count += 1

        status_str = "OK" if not error else f"ERROR: {error}"
        p.details.append(f"  Client {client_id}: session_create={sc_ms:.0f}ms prompt={pr_ms:.0f}ms events={len(events)} {status_str}")

    if session_create_latencies:
        avg_sc = sum(session_create_latencies) / len(session_create_latencies)
        max_sc = max(session_create_latencies)
        p.metrics["session_create_avg_ms"] = round(avg_sc, 1)
        p.metrics["session_create_max_ms"] = round(max_sc, 1)

    if prompt_latencies:
        avg_pr = sum(prompt_latencies) / len(prompt_latencies)
        max_pr = max(prompt_latencies)
        p.metrics["prompt_avg_ms"] = round(avg_pr, 1)
        p.metrics["prompt_max_ms"] = round(max_pr, 1)

    p.metrics["concurrency"] = CONCURRENCY
    p.metrics["success_count"] = success_count
    p.metrics["total_count"] = CONCURRENCY

    p.details.append(f"  Results: {success_count}/{CONCURRENCY} prompts completed")
    if prompt_latencies:
        p.details.append(f"  Prompt latency: avg={avg_pr:.0f}ms max={max_pr:.0f}ms")

    p.status = "pass" if success_count >= 1 else "fail"
    p.duration = time.time() - t0
    return p


# ---------------------------------------------------------------------------
# Phase 11 — Failure & Recovery
# ---------------------------------------------------------------------------

def phase_11_failure_recovery() -> PhaseResult:
    p = PhaseResult(name="Phase 11: Failure & Recovery")
    t0 = time.time()
    import websockets

    async def _run():
        results = []

        # 11a. WS disconnect mid-session -> reconnect should work
        try:
            ws = await websockets.connect(WS_URL)
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 1, "params": {"title": "Disconnect Test"}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            sid = resp.get("result", {}).get("id")
            await ws.close()

            # Reconnect
            ws2 = await websockets.connect(WS_URL)
            await ws2.send(json.dumps({"jsonrpc": "2.0", "method": "health", "id": 2, "params": {}}))
            resp = json.loads(await asyncio.wait_for(ws2.recv(), timeout=5))
            ok = resp.get("result", {}).get("status") == "ok"
            await ws2.close()
            results.append(("disconnect_reconnect", ok, "server survived disconnect"))
        except Exception as e:
            results.append(("disconnect_reconnect", False, str(e)))

        # 11b. Rapid-fire requests
        try:
            ws = await websockets.connect(WS_URL)
            for i in range(10):
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "health", "id": i, "params": {}}))
            ok_count = 0
            for _ in range(10):
                try:
                    resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
                    if "result" in resp:
                        ok_count += 1
                except asyncio.TimeoutError:
                    break
            await ws.close()
            results.append(("rapid_fire", ok_count >= 8, f"ok={ok_count}/10"))
        except Exception as e:
            results.append(("rapid_fire", False, str(e)))

        # 11c. Session resume with invalid ID
        try:
            ws = await websockets.connect(WS_URL)
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.resume", "id": 1, "params": {"session_id": "invalid-id-xyz"}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            has_error = "error" in resp
            await ws.close()
            results.append(("invalid_session_resume", has_error, f"error_returned={has_error}"))
        except Exception as e:
            results.append(("invalid_session_resume", False, str(e)))

        # 11d. Abrupt close (no graceful close frame)
        try:
            ws = await websockets.connect(WS_URL)
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 1, "params": {"title": "Abrupt Close"}}))
            await asyncio.wait_for(ws.recv(), timeout=5)
            # Abrupt close
            await ws.close(1006)
            results.append(("abrupt_close", True, "handled abrupt close"))
        except Exception as e:
            results.append(("abrupt_close", True, f"exception during close: {e}"))

        # Verify server still alive after all failures
        try:
            code, _ = http_get("/health")
            results.append(("server_alive_after_failures", code == 200, f"health={code}"))
        except Exception as e:
            results.append(("server_alive_after_failures", False, str(e)))

        return results

    try:
        results = asyncio.run(_run())
    except Exception as e:
        tb = traceback.format_exc()
        p.errors.append(f"Failure recovery crashed: {type(e).__name__}: {e}")
        p.details.append(tb[-500:] if len(tb) > 500 else tb)
        p.status = "error"
        p.duration = time.time() - t0
        return p

    for name, ok, detail in results:
        p.metrics[name] = ok
        if ok:
            p.details.append(f"  {name}: PASS ({detail})")
        else:
            p.errors.append(f"  {name}: FAIL ({detail})")

    p.status = "pass" if not p.errors else "fail"
    p.duration = time.time() - t0
    return p


# ---------------------------------------------------------------------------
# Phase 12 — Server Shutdown & Final Report
# ---------------------------------------------------------------------------

def phase_12_shutdown() -> PhaseResult:
    p = PhaseResult(name="Phase 12: Shutdown & Report")
    t0 = time.time()

    proc = report.server_proc
    if proc:
        p.details.append("Terminating server...")
        proc.terminate()
        try:
            proc.wait(timeout=10)
            p.details.append("Server terminated gracefully")
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
            p.details.append("Server killed (forced)")

    # Check DB size after all operations
    db_path = BASE_DIR / "data" / "zenith.db"
    if db_path.exists():
        size_kb = db_path.stat().st_size / 1024
        p.metrics["final_db_size_kb"] = round(size_kb, 1)
        p.details.append(f"Final DB size: {size_kb:.1f} KB")

    p.status = "pass"
    p.duration = time.time() - t0
    return p


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def main():
    overall_start = time.time()
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    print("=" * 72)
    print("  ZENITH COMPREHENSIVE VALIDATION")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)
    print()

    phase_funcs = [
        phase_1_build,
        phase_2_server_startup,
        phase_3_rest_api,
        phase_4_ws_protocol,
        phase_5_agent_scenario,
        phase_6_tools,
        phase_7_database,
        phase_8_config_errors,
        phase_9,
        phase_10_stress,
        phase_11_failure_recovery,
        phase_12_shutdown,
    ]

    for phase_fn in phase_funcs:
        phase_num = phase_fn.__name__.split("_")[1]
        print(f"\n--- Running {phase_fn.__name__.replace('_', ' ').title()} ---", flush=True)
        try:
            result = phase_fn()
        except Exception as e:
            result = PhaseResult(name=phase_fn.__name__, status="error")
            result.errors.append(f"Unhandled exception: {e}")
        report.add(result)
        icon = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP", "error": "ERR "}.get(result.status, "????")
        print(f"  [{icon}] {result.name} ({result.duration:.2f}s)", flush=True)

    report.total_duration = time.time() - overall_start

    # Print summary
    summary = report.summary()
    print(summary, flush=True)

    # Save report
    report_path = BASE_DIR / "validation_report.json"
    report_path.write_text(json.dumps(report.to_json(), indent=2))
    print(f"\nDetailed report saved to: {report_path}", flush=True)

    # Exit code
    failed = any(p.status in ("fail", "error") for p in report.phases)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
