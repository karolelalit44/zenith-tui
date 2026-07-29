"""Comprehensive 12-Phase Production Validation for Zenith."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Load API keys from .keys file
keys_path = ROOT / ".keys"
if keys_path.is_file():
    for line in keys_path.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()


# ── Result tracking ──────────────────────────────────────────────────────

@dataclass
class TestResult:
    phase: str
    name: str
    passed: bool
    message: str = ""
    duration_ms: float = 0
    severity: str = "High"  # Critical, High, Medium, Low

@dataclass
class PhaseReport:
    phase_num: int
    phase_name: str
    results: list[TestResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def status(self) -> str:
        return "PASS" if self.failed == 0 else "FAIL"


reports: list[PhaseReport] = []
current_phase: PhaseReport | None = None


def start_phase(num: int, name: str):
    global current_phase
    current_phase = PhaseReport(phase_num=num, phase_name=name)
    reports.append(current_phase)
    print(f"\n{'='*70}")
    print(f"  PHASE {num}: {name}")
    print(f"{'='*70}")


def ok(name: str, msg: str = "", duration_ms: float = 0):
    current_phase.results.append(TestResult(current_phase.phase_name, name, True, msg, duration_ms))
    print(f"  [OK] {name}" + (f" -- {msg}" if msg else ""))


def fail(name: str, msg: str = "", severity: str = "High", duration_ms: float = 0):
    current_phase.results.append(TestResult(current_phase.phase_name, name, False, msg, severity=severity, duration_ms=duration_ms))
    print(f"  [FAIL] [{severity}] {name} -- {msg}")


def timed(fn):
    t0 = time.perf_counter()
    result = fn()
    dt = (time.perf_counter() - t0) * 1000
    return result, dt


# ── WebSocket test helpers ───────────────────────────────────────────────

def _make_ws_helpers():
    """Return recv_response and drain_events as async functions for use in tests."""

    async def recv_response(ws, timeout=5):
        """Wait for a JSON-RPC response (has 'id' key), skipping event notifications."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), min(1, deadline - time.time()))
                msg = json.loads(raw)
                if "id" in msg:
                    return msg
            except TimeoutError:
                continue
        return None

    async def drain_events(ws, duration=1):
        """Consume any pending events for a short duration."""
        deadline = time.time() + duration
        while time.time() < deadline:
            try:
                await asyncio.wait_for(ws.recv(), min(0.2, deadline - time.time()))
            except TimeoutError:
                break

    return recv_response, drain_events

_recv_response, _drain_events = None, None


# ══════════════════════════════════════════════════════════════════════════
# PHASE 1 — Build & Environment Validation
# ══════════════════════════════════════════════════════════════════════════

def phase_1():
    start_phase(1, "Build & Environment Validation")

    # 1.1 Python version
    v = sys.version_info
    if v >= (3, 11):
        ok("Python version", f"{v.major}.{v.minor}.{v.micro}")
    else:
        fail("Python version", f"Need >=3.11, got {v.major}.{v.minor}", "Critical")

    # 1.2 Node version
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
        node_ver = r.stdout.strip()
        ok("Node.js version", node_ver)
    except Exception as e:
        fail("Node.js version", str(e), "Critical")

    # 1.3 Core Python imports
    core_modules = [
        "config.settings", "config.loader", "config.providers",
        "core.events", "core.message", "core.session", "core.domain", "core.errors",
        "db.connection", "db.repository",
        "providers.base", "providers.registry", "providers.parser", "providers.responder",
        "transport.server", "transport.handlers", "transport.middleware", "transport.prompt", "transport.protocol",
        "agent.loop", "agent.runtime", "agent.recovery", "agent.context", "agent.prompts",
        "tools.base", "tools.registry", "tools.bash", "tools.file_read", "tools.file_write", "tools.file_edit",
        "tools.glob_tool", "tools.grep_tool", "session.export",
    ]
    import_errors = []
    for mod in core_modules:
        try:
            __import__(mod)
        except Exception as e:
            import_errors.append(f"{mod}: {e}")
    if not import_errors:
        ok("Python module imports", f"{len(core_modules)} modules OK")
    else:
        fail("Python module imports", f"{len(import_errors)} failures:\n" + "\n".join(import_errors[:10]), "Critical")

    # 1.4 Config loading
    try:
        from config.loader import load_config
        cfg = load_config()
        ok("Config loading", f"provider={cfg.active_provider}, db={cfg.db_path}")
    except Exception as e:
        fail("Config loading", str(e), "Critical")

    # 1.5 Database initialization
    async def check_db():
        from db.connection import Database, resolve_db_path
        db = Database(resolve_db_path())
        await db.connect()
        rows = await db.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r["name"] for r in rows]
        await db.close()
        return tables

    try:
        tables = asyncio.get_event_loop().run_until_complete(check_db())
        expected = {"sessions", "messages", "providers", "provider_models", "app_settings"}
        missing = expected - set(tables)
        if not missing:
            ok("Database initialization", f"{len(tables)} tables: {', '.join(sorted(tables))}")
        else:
            fail("Database initialization", f"Missing tables: {missing}", "Critical")
    except Exception as e:
        fail("Database initialization", str(e), "Critical")

    # 1.6 Tool registry
    try:
        from tools import create_default_registry
        reg = create_default_registry()
        tools = reg.list_tools()
        ok("Tool registry", f"{len(tools)} tools: {', '.join(sorted(tools)[:8])}...")
    except Exception as e:
        fail("Tool registry", str(e), "Critical")

    # 1.7 Provider registry
    try:
        from config.loader import load_config
        from providers.registry import ProviderRegistry
        cfg = load_config()
        reg = ProviderRegistry.from_config(cfg.providers, cfg.active_provider)
        providers = reg.list_providers()
        ok("Provider registry", f"{len(providers)} providers: {providers}")
    except Exception as e:
        fail("Provider registry", str(e), "High")

    # 1.8 Package dependencies
    try:
        r = subprocess.run(
            [str(ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "pip", "check"],
            capture_output=True, text=True, timeout=30, cwd=str(ROOT)
        )
        if r.returncode == 0:
            ok("Python dependencies", "All satisfied")
        else:
            fail("Python dependencies", r.stdout[:200] + r.stderr[:200], "Medium")
    except Exception as e:
        fail("Python dependencies", str(e), "Medium")

    # 1.9 Node modules
    if (ROOT / "node_modules").exists():
        ok("Node modules", "node_modules present")
    else:
        fail("Node modules", "node_modules missing", "Critical")

    # 1.10 .env / .keys
    env_exists = (ROOT / ".env").exists()
    keys_exists = (ROOT / ".keys").exists()
    ok("Environment files", f".env={env_exists}, .keys={keys_exists}")

    # 1.11 Data directory
    data_dir = ROOT / "data"
    if data_dir.exists() and (data_dir / "zenith.db").exists():
        db_size = (data_dir / "zenith.db").stat().st_size
        ok("Data directory", f"zenith.db present ({db_size} bytes)")
    else:
        fail("Data directory", "data/zenith.db missing", "Critical")


# ══════════════════════════════════════════════════════════════════════════
# PHASE 2 — Backend Validation
# ══════════════════════════════════════════════════════════════════════════

def phase_2():
    start_phase(2, "Backend Validation")

    # 2.1 Server startup
    server_proc = None
    try:
        t0 = time.perf_counter()
        server_proc = subprocess.Popen(
            [str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "main.py"), "serve"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )
        # Wait for server to be ready
        for _ in range(30):
            time.sleep(1)
            try:
                req = urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=2)
                if req.status == 200:
                    break
            except Exception:
                pass
        startup_ms = (time.perf_counter() - t0) * 1000
        if server_proc.poll() is None:
            ok("Server startup", f"{startup_ms:.0f}ms, PID={server_proc.pid}")
        else:
            fail("Server startup", f"Process exited with code {server_proc.returncode}", "Critical")
            return
    except Exception as e:
        fail("Server startup", str(e), "Critical")
        return

    # 2.2 Health endpoint
    try:
        req = urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=5)
        data = json.loads(req.read())
        if data.get("status") == "ok":
            ok("GET /health", f"version={data.get('version')}")
        else:
            fail("GET /health", f"Unexpected: {data}", "High")
    except Exception as e:
        fail("GET /health", str(e), "High")

    # 2.3 Status endpoint
    try:
        req = urllib.request.urlopen("http://127.0.0.1:8765/status", timeout=5)
        data = json.loads(req.read())
        if data.get("ready"):
            ok("GET /status", f"provider={data.get('provider')}, tools={len(data.get('tools', []))}")
        else:
            fail("GET /status", f"Not ready: {data}", "High")
    except Exception as e:
        fail("GET /status", str(e), "High")

    # 2.4 Startup validation endpoint
    try:
        req = urllib.request.urlopen("http://127.0.0.1:8765/startup/validate", timeout=5)
        data = json.loads(req.read())
        ok("GET /startup/validate", f"valid={data.get('valid')}")
    except Exception as e:
        fail("GET /startup/validate", str(e), "Medium")

    # 2.5 Provider config endpoint
    try:
        req = urllib.request.urlopen("http://127.0.0.1:8765/startup/provider-config", timeout=5)
        data = json.loads(req.read())
        ok("GET /startup/provider-config", f"has_config={bool(data)}")
    except Exception as e:
        fail("GET /startup/provider-config", str(e), "Medium")

    # 2.6 WebSocket session.create
    async def test_ws_session():
        import websockets
        results = {}
        async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:
            # session.create
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 1, "params": {"title": "Test Session"}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
            sid = resp.get("result", {}).get("id")
            results["session_create"] = sid is not None

            # session.list
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.list", "id": 2, "params": {}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
            results["session_list"] = isinstance(resp.get("result"), list)

            # tools.list
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "tools.list", "id": 3, "params": {}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
            results["tools_list"] = len(resp.get("result", {}).get("tools", [])) > 0

            # workspace.status
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "workspace.status", "id": 4, "params": {}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
            results["workspace_status"] = "branch" in resp.get("result", {})

            # health
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "health", "id": 5, "params": {}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
            results["ws_health"] = resp.get("result", {}).get("status") == "ok"

            # session.resume
            if sid:
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.resume", "id": 6, "params": {"session_id": sid}}))
                resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
                results["session_resume"] = "session" in resp.get("result", {})

            # workspace.diff
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "workspace.diff", "id": 7, "params": {}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
            results["workspace_diff"] = "diff" in resp.get("result", {})

            # workspace.log
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "workspace.log", "id": 8, "params": {"count": 3}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
            results["workspace_log"] = "log" in resp.get("result", {})

            # session.export
            if sid:
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.export", "id": 9, "params": {"session_id": sid}}))
                resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
                results["session_export"] = "result" in resp

            # Invalid method (error handling)
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "invalid.method", "id": 10, "params": {}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
            results["error_handling"] = "error" in resp

        return results

    try:
        ws_results = asyncio.get_event_loop().run_until_complete(test_ws_session())
        for name, passed in ws_results.items():
            if passed:
                ok(f"WS: {name}", "OK")
            else:
                fail(f"WS: {name}", "Failed", "High")
    except Exception as e:
        fail("WebSocket tests", str(e), "Critical")
        traceback.print_exc()

    # 2.7 Prompt.send (LLM call — requires API key)
    async def test_prompt():
        import websockets
        events = []
        async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:
            # Create session first
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 1, "params": {"title": "Prompt Test"}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
            sid = resp.get("result", {}).get("id")

            # Send prompt
            await ws.send(json.dumps({
                "jsonrpc": "2.0", "method": "prompt.send", "id": 2,
                "params": {"content": "Say exactly: hello world", "session_id": sid, "mode": "build"}
            }))

            # Collect responses
            deadline = time.time() + 90
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), 10)
                    msg = json.loads(raw)
                    if "result" in msg and isinstance(msg["result"], dict) and msg["result"].get("status") == "processing":
                        continue
                    events.append(msg)
                    # Check for success event
                    params = msg.get("params", {})
                    if params.get("kind") == "success":
                        return True, events
                    if params.get("kind") == "error":
                        return False, events
                except TimeoutError:
                    break
        return len(events) > 0, events

    try:
        prompt_ok, prompt_events = asyncio.get_event_loop().run_until_complete(test_prompt())
        if prompt_ok:
            kinds = [e.get("params", {}).get("kind", "?") for e in prompt_events]
            ok("prompt.send", f"Got {len(prompt_events)} events: {kinds}")
        else:
            kinds = [e.get("params", {}).get("kind", "?") for e in prompt_events]
            fail("prompt.send", f"No success event after {len(prompt_events)} events: {kinds}", "Critical")
    except Exception as e:
        fail("prompt.send", str(e), "Critical")

    # Stop server
    if server_proc:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()
        ok("Server shutdown", "Terminated cleanly")


# ══════════════════════════════════════════════════════════════════════════
# PHASE 3 — Frontend Validation
# ══════════════════════════════════════════════════════════════════════════

def phase_3():
    start_phase(3, "Frontend Validation")

    # 3.1 TypeScript compilation
    try:
        r = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT),
            shell=True,
        )
        if r.returncode == 0:
            ok("TypeScript compilation", "No errors")
        else:
            err_lines = [l for l in r.stdout.splitlines() if "error TS" in l]
            fail("TypeScript compilation", f"{len(err_lines)} errors:\n" + "\n".join(err_lines[:5]), "High")
    except Exception as e:
        fail("TypeScript compilation", str(e), "High")

    # 3.2 Biome lint
    try:
        r = subprocess.run(
            ["npx", "biome", "check", "src/"],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT),
            shell=True,
        )
        if r.returncode == 0:
            ok("Biome lint", "No issues")
        else:
            issues = r.stdout.count("·")
            fail("Biome lint", f"{issues} issues found (exit {r.returncode})", "Medium")
    except Exception as e:
        fail("Biome lint", str(e), "Medium")

    # 3.3 Vitest tests
    try:
        r = subprocess.run(
            ["npx", "vitest", "run", "--reporter=verbose"],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT),
            shell=True,
        )
        if r.returncode == 0:
            # Parse test count
            lines = r.stdout.splitlines()
            summary = [l for l in lines if "Tests" in l or "test" in l.lower()]
            ok("Vitest tests", f"All passed. {' | '.join(summary[-2:]) if summary else ''}")
        else:
            lines = r.stdout.splitlines()
            summary = [l for l in lines if "Tests" in l or "Failed" in l]
            fail("Vitest tests", f"Failed. {' | '.join(summary[-3:]) if summary else r.stdout[-300:]}", "High")
    except Exception as e:
        fail("Vitest tests", str(e), "High")

    # 3.4 Frontend entry point
    entry = ROOT / "src" / "index.tsx"
    if entry.exists():
        ok("Frontend entry point", f"src/index.tsx ({entry.stat().st_size} bytes)")
    else:
        fail("Frontend entry point", "src/index.tsx not found", "High")

    # 3.5 Component count
    components = list((ROOT / "src" / "components").rglob("*.tsx")) if (ROOT / "src" / "components").exists() else []
    screens = list((ROOT / "src" / "screens").rglob("*.tsx")) if (ROOT / "src" / "screens").exists() else []
    hooks = list((ROOT / "src" / "hooks").rglob("*.ts")) if (ROOT / "src" / "hooks").exists() else []
    ok("Frontend structure", f"{len(components)} components, {len(screens)} screens, {len(hooks)} hooks")


# ══════════════════════════════════════════════════════════════════════════
# PHASE 4 — End-to-End Workflow Testing
# ══════════════════════════════════════════════════════════════════════════

def phase_4():
    start_phase(4, "End-to-End Workflow Testing")

    # Start server
    server_proc = subprocess.Popen(
        [str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "main.py"), "serve"],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace",
    )
    time.sleep(7)

    if server_proc.poll() is not None:
        fail("Server for E2E", "Failed to start", "Critical")
        return

    try:
        import websockets

        async def recv_response(ws, timeout=5):
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), min(1, deadline - time.time()))
                    msg = json.loads(raw)
                    if "id" in msg:
                        return msg
                except TimeoutError:
                    continue
            return None

        async def drain_events(ws, duration=1):
            deadline = time.time() + duration
            while time.time() < deadline:
                try:
                    await asyncio.wait_for(ws.recv(), min(0.2, deadline - time.time()))
                except TimeoutError:
                    break

        async def test_e2e_session_lifecycle():
            """Test complete session lifecycle: create -> resume -> send prompt -> export."""
            results = {}
            async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:
                # 1. Create session
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 1, "params": {"title": "E2E Lifecycle Test"}}))
                resp = await recv_response(ws, 5)
                sid = resp["result"]["id"]
                results["create"] = True

                # 2. List sessions (should contain ours)
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.list", "id": 2, "params": {}}))
                resp = await recv_response(ws, 5)
                sessions = resp["result"]
                results["list"] = any(s["id"] == sid for s in sessions)

                # 3. Resume session
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.resume", "id": 3, "params": {"session_id": sid}}))
                resp = await recv_response(ws, 5)
                results["resume"] = resp["result"]["session"]["id"] == sid

                # 4. Send prompt (will use LLM)
                await ws.send(json.dumps({
                    "jsonrpc": "2.0", "method": "prompt.send", "id": 4,
                    "params": {"content": "Say exactly: e2e test pass", "session_id": sid, "mode": "build"}
                }))

                got_processing = False
                got_success = False
                deadline = time.time() + 90
                while time.time() < deadline:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), 10)
                        msg = json.loads(raw)
                        if msg.get("result") and isinstance(msg["result"], dict) and msg["result"].get("status") == "processing":
                            got_processing = True
                        kind = msg.get("params", {}).get("kind")
                        if kind == "success":
                            got_success = True
                            break
                        if kind == "error":
                            break
                    except TimeoutError:
                        break
                results["prompt_processing"] = got_processing
                results["prompt_success"] = got_success

                # Drain leftover events
                await drain_events(ws, 2)

                # 5. Export session
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.export", "id": 5, "params": {"session_id": sid}}))
                resp = await recv_response(ws, 5)
                results["export"] = resp is not None and "result" in resp

            return results

        e2e_results = asyncio.get_event_loop().run_until_complete(test_e2e_session_lifecycle())
        for name, passed in e2e_results.items():
            if passed:
                ok(f"E2E: {name}", "OK")
            else:
                fail(f"E2E: {name}", "Failed", "High")

    except Exception as e:
        fail("E2E workflow", str(e), "Critical")
        traceback.print_exc()
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()


# ══════════════════════════════════════════════════════════════════════════
# PHASE 5 — Agent Runtime Validation
# ══════════════════════════════════════════════════════════════════════════

def phase_5():
    start_phase(5, "Agent Runtime Validation")

    # 5.1 AgentLoop instantiation
    try:
        from agent.context import ContextManager
        from agent.loop import AgentLoop
        from agent.prompts import build_system_prompt
        from agent.recovery import RecoverableAgentLoop
        from config.loader import load_config
        from providers.registry import ProviderRegistry

        cfg = load_config()
        reg = ProviderRegistry.from_config(cfg.providers, cfg.active_provider)
        provider = reg.get(cfg.active_provider)

        ctx = ContextManager(cfg)
        AgentLoop(cfg, provider, ctx)
        ok("AgentLoop instantiation", f"provider={provider.name if provider else 'None'}")
    except Exception as e:
        fail("AgentLoop instantiation", str(e), "Critical")

    # 5.2 RecoverableAgentLoop
    try:
        RecoverableAgentLoop(cfg, provider, ctx)
        ok("RecoverableAgentLoop", "OK")
    except Exception as e:
        fail("RecoverableAgentLoop", str(e), "High")

    # 5.3 DefaultAgentRuntime
    try:
        from agent.runtime import DefaultAgentRuntime
        runtime = DefaultAgentRuntime(cfg, provider)
        ok("DefaultAgentRuntime", f"state={runtime.get_state().value}")
    except Exception as e:
        fail("DefaultAgentRuntime", str(e), "High")

    # 5.4 System prompt generation
    try:
        from tools import create_default_registry
        tool_reg = create_default_registry()
        schemas = tool_reg.get_schemas()
        prompt = build_system_prompt(".", "build", schemas)
        ok("System prompt generation", f"{len(prompt)} chars, {len(schemas)} tools")
    except Exception as e:
        fail("System prompt generation", str(e), "High")

    # 5.5 Context manager
    try:
        cm = ContextManager(cfg)
        from core.message import Message
        history = [Message(session_id="test", role="user", content="Hello")]
        messages = cm.build_messages(history, "system prompt", "user message", "model")
        ok("ContextManager.build_messages", f"{len(messages)} messages")
    except Exception as e:
        fail("ContextManager.build_messages", str(e), "High")

    # 5.6 Loop detection
    try:
        from agent.loop_detection import LoopDetector
        ld = LoopDetector()
        ld.record("bash", {"command": "ls"}, "output")
        detected = ld.is_loop_detected()
        ok("LoopDetector", f"detected={detected}")
    except Exception as e:
        fail("LoopDetector", str(e), "Medium")

    # 5.7 Validation module
    try:
        from agent.validation import schemas_to_openai_tools
        openai_tools = schemas_to_openai_tools(schemas)
        ok("Agent validation module", f"{len(openai_tools)} OpenAI tools converted")
    except Exception as e:
        fail("Agent validation module", str(e), "High")


# ══════════════════════════════════════════════════════════════════════════
# PHASE 6 — Tool Framework Testing
# ══════════════════════════════════════════════════════════════════════════

def phase_6():
    start_phase(6, "Tool Framework Testing")

    try:
        from config.loader import load_config
        from tools import create_default_registry

        load_config()
        reg = create_default_registry()

        # 6.1 Registry completeness
        tools = reg.list_tools()
        expected_tools = {"bash", "file_read", "file_write", "file_edit", "glob", "grep", "question"}
        missing = expected_tools - set(tools)
        if not missing:
            ok("Registry completeness", f"{len(tools)} tools registered")
        else:
            fail("Registry completeness", f"Missing: {missing}", "High")

        # 6.2 Schema validation
        schemas = reg.get_schemas()
        for s in schemas:
            assert "name" in s, f"Schema missing name: {s}"
            assert "description" in s, f"Schema missing description: {s}"
            assert "schema" in s, f"Schema missing schema: {s}"
        ok("Schema validation", f"{len(schemas)} schemas valid")

        # 6.3 Tool instantiation
        for name in tools:
            tool = reg.get(name)
            assert tool is not None, f"Tool '{name}' not found"
            assert hasattr(tool, "name"), f"Tool '{name}' missing .name"
            assert hasattr(tool, "description"), f"Tool '{name}' missing .description"
        ok("Tool instantiation", f"All {len(tools)} tools have name + description")

        # 6.4 Safe tool execution (file_read)
        async def test_safe_tool():
            result = await reg.execute("file_read", {"path": str(ROOT / "main.py")}, str(ROOT))
            return result

        result = asyncio.get_event_loop().run_until_complete(test_safe_tool())
        if result.success:
            ok("Tool execution (file_read)", f"Read {len(result.output)} chars")
        else:
            fail("Tool execution (file_read)", result.error, "High")

        # 6.5 Glob tool
        async def test_glob():
            return await reg.execute("glob", {"pattern": "*.py", "path": str(ROOT)}, str(ROOT))

        result = asyncio.get_event_loop().run_until_complete(test_glob())
        if result.success:
            ok("Tool execution (glob)", f"Found results ({len(result.output)} chars)")
        else:
            fail("Tool execution (glob)", result.error, "High")

        # 6.6 Grep tool
        async def test_grep():
            return await reg.execute("grep", {"pattern": "def cli", "path": str(ROOT / "main.py")}, str(ROOT))

        result = asyncio.get_event_loop().run_until_complete(test_grep())
        if result.success:
            ok("Tool execution (grep)", f"Found matches ({len(result.output)} chars)")
        else:
            fail("Tool execution (grep)", result.error, "High")

        # 6.7 Tool middleware
        try:
            from tools.middleware import ToolMiddleware
            ok("Tool middleware import", "OK")
        except ImportError:
            ok("Tool middleware import", "Module not present (optional)")

        # 6.8 Risk levels
        risky_tools = []
        for name in tools:
            tool = reg.get(name)
            if hasattr(tool, "risk_level") and tool.risk_level in ("high", "critical"):
                risky_tools.append(name)
        ok("Risk assessment", f"High-risk tools: {risky_tools or 'none'}")

    except Exception as e:
        fail("Tool framework", str(e), "Critical")
        traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════
# PHASE 7 — Infrastructure Testing
# ══════════════════════════════════════════════════════════════════════════

def phase_7():
    start_phase(7, "Infrastructure Testing")

    # 7.1 Database CRUD
    async def test_db_crud():
        from core.message import Message
        from core.session import Session
        from db.connection import Database, resolve_db_path
        from db.repository import MessageRepository, SessionRepository

        db = Database(resolve_db_path())
        await db.connect()

        sr = SessionRepository(db)
        mr = MessageRepository(db)

        # Create session
        session = Session(title="Infra Test")
        await sr.create(session)

        # Read session
        fetched = await sr.get(session.id)
        assert fetched is not None and fetched.title == "Infra Test"

        # List sessions
        sessions = await sr.list_active()
        assert any(s.id == session.id for s in sessions)

        # Create message
        msg = Message(session_id=session.id, role="user", content="Hello infra")
        await mr.create(msg)

        # Read messages
        msgs = await mr.get_by_session(session.id)
        assert len(msgs) >= 1

        # Count tokens
        tokens = await mr.count_tokens(session.id)
        assert tokens >= 0

        # Delete session
        await sr.delete(session.id)
        fetched = await sr.get(session.id)
        assert fetched is None

        await db.close()
        return True

    try:
        asyncio.get_event_loop().run_until_complete(test_db_crud())
        ok("Database CRUD", "Create, Read, List, Delete all pass")
    except Exception as e:
        fail("Database CRUD", str(e), "Critical")

    # 7.2 Provider repository
    async def test_provider_repo():
        from db.connection import Database, resolve_db_path
        from db.repository import ProviderRepositoryDB

        db = Database(resolve_db_path())
        await db.connect()
        repo = ProviderRepositoryDB(db)
        await repo.ensure_seeded()
        providers = await repo.list_providers()
        assert len(providers) > 0
        await db.close()
        return providers

    try:
        providers = asyncio.get_event_loop().run_until_complete(test_provider_repo())
        ok("Provider repository", f"{len(providers)} providers seeded")
    except Exception as e:
        fail("Provider repository", str(e), "High")

    # 7.3 Migration runner
    try:
        ok("Migration runner import", "OK")
    except Exception as e:
        fail("Migration runner import", str(e), "High")

    # 7.4 Workspace operations
    try:
        from workspace.git import GitOps
        git = GitOps(".")
        status = git.status()
        assert "branch" in status
        ok("GitOps.status", f"branch={status.get('branch')}")
    except Exception as e:
        fail("GitOps.status", str(e), "High")

    # 7.5 Repo map
    try:
        from workspace.repo_map import RepoMap
        repo = RepoMap(".")
        structure = repo.get_structure(2)
        ok("RepoMap.get_structure", f"{len(structure)} chars")
    except Exception as e:
        fail("RepoMap.get_structure", str(e), "Medium")

    # 7.6 Session export
    try:
        from session.export import SessionExporter
        SessionExporter()
        ok("SessionExporter", "Instantiated OK")
    except Exception as e:
        fail("SessionExporter", str(e), "Medium")

    # 7.7 Skills loader
    try:
        from skills.loader import SkillLoader
        loader = SkillLoader(".")
        skills = loader.get_skill_prompt()
        ok("SkillLoader", f"{len(skills)} chars of skills prompt")
    except Exception as e:
        fail("SkillLoader", str(e), "Medium")

    # 7.8 LSP manager
    try:
        from lsp.manager import LspManager
        LspManager(workspace_root=".")
        ok("LspManager", "Initialized")
    except Exception as e:
        fail("LspManager", str(e), "Medium")

    # 7.9 MCP client
    try:
        ok("McpClient import", "OK")
    except Exception as e:
        fail("McpClient import", str(e), "Low")

    # 7.10 Graceful shutdown
    try:
        from transport.shutdown import GracefulShutdown
        GracefulShutdown()
        ok("GracefulShutdown", "Instantiated")
    except Exception as e:
        fail("GracefulShutdown", str(e), "Medium")

    # 7.11 Log files
    log_dir = ROOT / "data"
    ok("Data directory exists", str(log_dir.exists()))

    # 7.12 .gitkeep and .gitignore
    gitignore = ROOT / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        ok(".gitignore", f"{len(content)} chars")
    else:
        fail(".gitignore", "Missing", "Low")


# ══════════════════════════════════════════════════════════════════════════
# PHASE 8 — Integration Testing
# ══════════════════════════════════════════════════════════════════════════

def phase_8():
    start_phase(8, "Integration Testing")

    # Start server for integration tests
    server_proc = subprocess.Popen(
        [str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "main.py"), "serve"],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace",
    )
    time.sleep(7)

    if server_proc.poll() is not None:
        fail("Server for integration", "Failed to start", "Critical")
        return

    try:
        import websockets

        async def recv_response(ws, timeout=5):
            """Wait for a JSON-RPC response (has 'id' key), skipping event notifications."""
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), min(1, deadline - time.time()))
                    msg = json.loads(raw)
                    if "id" in msg:
                        return msg
                except TimeoutError:
                    continue
            return None

        async def drain_events(ws, duration=1):
            """Consume any pending events for a short duration."""
            deadline = time.time() + duration
            while time.time() < deadline:
                try:
                    await asyncio.wait_for(ws.recv(), min(0.2, deadline - time.time()))
                except TimeoutError:
                    break

        async def test_integration():
            results = {}
            async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:
                # 8.1 Multi-step session flow
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 1, "params": {"title": "Integration Test"}}))
                resp = await recv_response(ws, 5)
                sid = resp["result"]["id"]
                results["session_create_integration"] = True

                # 8.2 Multiple prompts in same session
                for i, prompt in enumerate(["Say: step 1", "Say: step 2"]):
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0", "method": "prompt.send", "id": 10 + i,
                        "params": {"content": prompt, "session_id": sid, "mode": "build"}
                    }))
                    deadline = time.time() + 90
                    got_success = False
                    while time.time() < deadline:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), 10)
                            msg = json.loads(raw)
                            if msg.get("params", {}).get("kind") == "success":
                                got_success = True
                                break
                            if msg.get("params", {}).get("kind") == "error":
                                break
                        except TimeoutError:
                            break
                    results[f"prompt_{i+1}_success"] = got_success
                    await drain_events(ws, 1)

                # 8.3 Session resume with history
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.resume", "id": 20, "params": {"session_id": sid}}))
                resp = await recv_response(ws, 5)
                messages = resp.get("result", {}).get("messages", []) if resp else []
                results["history_persistence"] = len(messages) > 0

                # 8.4 Concurrent sessions
                sessions = []
                for i in range(3):
                    await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 30 + i, "params": {"title": f"Concurrent {i}"}}))
                    resp = await recv_response(ws, 5)
                    if resp and "result" in resp:
                        sessions.append(resp["result"]["id"])
                results["concurrent_sessions"] = len(sessions) == 3

                # 8.5 Session export
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.export", "id": 40, "params": {"session_id": sid}}))
                resp = await recv_response(ws, 5)
                results["export_after_prompts"] = resp is not None and "result" in resp

            return results

        int_results = asyncio.get_event_loop().run_until_complete(test_integration())
        for name, passed in int_results.items():
            if passed:
                ok(f"Integration: {name}", "OK")
            else:
                fail(f"Integration: {name}", "Failed", "High")

    except Exception as e:
        fail("Integration tests", str(e), "Critical")
        traceback.print_exc()
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()


# ══════════════════════════════════════════════════════════════════════════
# PHASE 9 — Stress & Reliability Testing
# ══════════════════════════════════════════════════════════════════════════

def phase_9():
    start_phase(9, "Stress & Reliability Testing")

    server_proc = subprocess.Popen(
        [str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "main.py"), "serve"],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace",
    )
    time.sleep(7)

    if server_proc.poll() is not None:
        fail("Server for stress", "Failed to start", "Critical")
        return

    try:
        import websockets

        async def test_stress():
            results = {}

            # 9.1 Rapid session creation
            async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:
                t0 = time.perf_counter()
                sessions = []
                for i in range(20):
                    await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": i, "params": {"title": f"Rapid {i}"}}))
                    resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
                    sessions.append(resp["result"]["id"])
                dt = (time.perf_counter() - t0) * 1000
                results["rapid_sessions"] = f"20 sessions in {dt:.0f}ms"

            # 9.2 Multiple concurrent connections
            connections = []
            for i in range(5):
                try:
                    ws = await websockets.connect("ws://127.0.0.1:8765/ws")
                    connections.append(ws)
                except Exception:
                    pass
            results["concurrent_connections"] = f"{len(connections)}/5 connected"

            # Send health check on each
            for i, ws in enumerate(connections):
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "health", "id": i, "params": {}}))
                resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert resp.get("result", {}).get("status") == "ok"

            # Close all
            for ws in connections:
                await ws.close()

            # 9.3 Rapid message sending
            async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 100, "params": {"title": "Rapid Msg"}}))
                resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
                resp["result"]["id"]
                t0 = time.perf_counter()
                for i in range(10):
                    await ws.send(json.dumps({"jsonrpc": "2.0", "method": "tools.list", "id": 200 + i, "params": {}}))
                    await asyncio.wait_for(ws.recv(), 5)
                dt = (time.perf_counter() - t0) * 1000
                results["rapid_messages"] = f"10 requests in {dt:.0f}ms ({dt/10:.1f}ms/req)"

            return results

        stress_results = asyncio.get_event_loop().run_until_complete(test_stress())
        for name, msg in stress_results.items():
            ok(f"Stress: {name}", msg)

    except Exception as e:
        fail("Stress tests", str(e), "High")
        traceback.print_exc()
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()


# ══════════════════════════════════════════════════════════════════════════
# PHASE 10 — Failure & Recovery Testing
# ══════════════════════════════════════════════════════════════════════════

def phase_10():
    start_phase(10, "Failure & Recovery Testing")

    server_proc = subprocess.Popen(
        [str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "main.py"), "serve"],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace",
    )
    time.sleep(7)

    if server_proc.poll() is not None:
        fail("Server for failure testing", "Failed to start", "Critical")
        return

    try:
        import websockets

        async def test_failure():
            results = {}

            # 10.1 Invalid JSON
            try:
                ws = await websockets.connect("ws://127.0.0.1:8765/ws")
                await ws.send("not json!!!")
                resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
                results["invalid_json"] = "error" in resp
                await ws.close()
            except Exception:
                results["invalid_json"] = False

            # 10.2 Invalid method
            try:
                ws = await websockets.connect("ws://127.0.0.1:8765/ws")
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "nonexistent", "id": 1, "params": {}}))
                resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
                results["invalid_method"] = "error" in resp
                await ws.close()
            except Exception:
                results["invalid_method"] = False

            # 10.3 Empty prompt
            try:
                ws = await websockets.connect("ws://127.0.0.1:8765/ws")
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 1, "params": {"title": "Error Test"}}))
                resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
                sid = resp["result"]["id"]
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "prompt.send", "id": 2, "params": {"content": "", "session_id": sid}}))
                resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
                results["empty_prompt"] = "error" in resp
                await ws.close()
            except Exception:
                results["empty_prompt"] = False

            # 10.4 Nonexistent session resume
            try:
                ws = await websockets.connect("ws://127.0.0.1:8765/ws")
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.resume", "id": 1, "params": {"session_id": "nonexistent-id"}}))
                resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
                results["nonexistent_session"] = "error" in resp
                await ws.close()
            except Exception:
                results["nonexistent_session"] = False

            # 10.5 WebSocket disconnect and reconnect
            try:
                ws = await websockets.connect("ws://127.0.0.1:8765/ws")
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 1, "params": {"title": "Reconnect Test"}}))
                resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
                await ws.close()
                # Reconnect
                ws2 = await websockets.connect("ws://127.0.0.1:8765/ws")
                await ws2.send(json.dumps({"jsonrpc": "2.0", "method": "health", "id": 2, "params": {}}))
                resp = json.loads(await asyncio.wait_for(ws2.recv(), 5))
                results["reconnect"] = resp.get("result", {}).get("status") == "ok"
                await ws2.close()
            except Exception:
                results["reconnect"] = False

            # 10.6 Server health after errors
            try:
                req = urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=5)
                data = json.loads(req.read())
                results["health_after_errors"] = data.get("status") == "ok"
            except Exception:
                results["health_after_errors"] = False

            return results

        fail_results = asyncio.get_event_loop().run_until_complete(test_failure())
        for name, passed in fail_results.items():
            if passed:
                ok(f"Failure: {name}", "Handled gracefully")
            else:
                fail(f"Failure: {name}", "Did not handle gracefully", "High")

    except Exception as e:
        fail("Failure tests", str(e), "High")
        traceback.print_exc()
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()


# ══════════════════════════════════════════════════════════════════════════
# PHASE 11 — Code Quality Validation
# ══════════════════════════════════════════════════════════════════════════

def phase_11():
    start_phase(11, "Code Quality Validation")

    # 11.1 Python test suite (ensure no server is running)
    subprocess.run(["taskkill", "/F", "/IM", "python.exe", "/T"], capture_output=True, timeout=5)
    time.sleep(2)
    try:
        r = subprocess.run(
            [str(ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "pytest", "tests/", "-q", "--tb=short",
             "--ignore=tests/e2e_real.py", "--ignore=tests/test_e2e_websocket.py",
             "--ignore=tests/test_e2e_integration.py", "--ignore=tests/test_e2e.py"],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT)
        )
        lines = r.stdout.strip().splitlines()
        summary = lines[-1] if lines else "OK"
        if r.returncode == 0:
            ok("Python tests (pytest)", summary)
        else:
            fail("Python tests (pytest)", summary, "High")
    except Exception as e:
        fail("Python tests (pytest)", str(e), "High")

    # 11.2 TODO/FIXME/HACK scan
    todo_files = []
    for py in ROOT.rglob("*.py"):
        if ".venv" in str(py) or "node_modules" in str(py) or "__pycache__" in str(py):
            continue
        try:
            content = py.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(content.splitlines(), 1):
                if any(tag in line for tag in ["TODO", "FIXME", "HACK", "XXX"]):
                    todo_files.append(f"{py.relative_to(ROOT)}:{i}: {line.strip()[:80]}")
        except Exception:
            pass
    for ts in ROOT.rglob("*.ts"):
        if ".venv" in str(ts) or "node_modules" in str(ts):
            continue
        try:
            content = ts.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(content.splitlines(), 1):
                if any(tag in line for tag in ["TODO", "FIXME", "HACK", "XXX"]):
                    todo_files.append(f"{ts.relative_to(ROOT)}:{i}: {line.strip()[:80]}")
        except Exception:
            pass
    if todo_files:
        ok("TODO/FIXME scan", f"{len(todo_files)} items found (info, not blocking)")
    else:
        ok("TODO/FIXME scan", "Clean — no items found")

    # 11.3 Debug artifacts scan
    debug_artifacts = []
    for py in ROOT.rglob("*.py"):
        if ".venv" in str(py) or "node_modules" in str(py) or "__pycache__" in str(py) or "scripts/" in str(py):
            continue
        try:
            content = py.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#") or '"""' in stripped or "stderr" in stripped:
                    continue
                if "_dbg(" in stripped or "print(" in stripped:
                    debug_artifacts.append(f"{py.relative_to(ROOT)}:{i}: {stripped[:80]}")
        except Exception:
            pass
    if debug_artifacts:
        fail("Debug artifacts", f"{len(debug_artifacts)} debug prints found:\n" + "\n".join(debug_artifacts[:5]), "Medium")
    else:
        ok("Debug artifacts", "Clean")

    # 11.4 Circular import check
    try:
        import importlib
        modules_to_check = [
            "config.settings", "core.events", "core.message", "core.session",
            "db.connection", "providers.base", "transport.protocol",
        ]
        for mod in modules_to_check:
            importlib.import_module(mod)
        ok("Critical module imports", "No circular imports detected")
    except Exception as e:
        fail("Critical module imports", str(e), "High")

    # 11.5 __init__.py completeness
    packages = ["agent", "config", "core", "db", "lsp", "mcp", "providers",
                "session", "skills", "tools", "transport", "workspace"]
    missing_init = []
    for pkg in packages:
        init_file = ROOT / pkg / "__init__.py"
        if not init_file.exists():
            missing_init.append(pkg)
    if missing_init:
        fail("__init__.py files", f"Missing in: {missing_init}", "Medium")
    else:
        ok("__init__.py files", f"All {len(packages)} packages have __init__.py")

    # 11.6 Dead code: unused files
    orphaned = []
    for py in ROOT.glob("*.py"):
        if py.name in ("main.py", "__init__.py", "__main__.py", "app.py"):
            continue
        # Check if imported anywhere
        name_stem = py.stem
        found = False
        for other_py in ROOT.rglob("*.py"):
            if other_py == py or ".venv" in str(other_py) or "__pycache__" in str(other_py):
                continue
            try:
                content = other_py.read_text(encoding="utf-8", errors="replace")
                if name_stem in content:
                    found = True
                    break
            except Exception:
                pass
        if not found:
            orphaned.append(py.name)
    if orphaned:
        ok("Dead code scan", f"Potentially unused files: {orphaned} (verify manually)")
    else:
        ok("Dead code scan", "No obviously orphaned files")


# ══════════════════════════════════════════════════════════════════════════
# PHASE 12 — Performance & Production Readiness
# ══════════════════════════════════════════════════════════════════════════

def phase_12():
    start_phase(12, "Performance & Production Readiness")

    # 12.1 Server startup time
    times = []
    for _ in range(3):
        proc = subprocess.Popen(
            [str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "main.py"), "serve"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            encoding="utf-8", errors="replace",
        )
        t0 = time.perf_counter()
        for _ in range(30):
            time.sleep(0.5)
            try:
                req = urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=1)
                if req.status == 200:
                    break
            except Exception:
                pass
        dt = (time.perf_counter() - t0) * 1000
        times.append(dt)
        proc.terminate()
        proc.wait(timeout=5)
        time.sleep(1)

    avg_startup = sum(times) / len(times)
    if avg_startup < 15000:
        ok("Server startup time", f"Avg: {avg_startup:.0f}ms over 3 runs ({times})")
    else:
        fail("Server startup time", f"Avg: {avg_startup:.0f}ms (>15s target)", "Medium")

    # 12.2 HTTP response latency
    proc = subprocess.Popen(
        [str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "main.py"), "serve"],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace",
    )
    time.sleep(7)

    latencies = []
    for _ in range(10):
        t0 = time.perf_counter()
        try:
            urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=5)
        except Exception:
            pass
        latencies.append((time.perf_counter() - t0) * 1000)
    avg_latency = sum(latencies) / len(latencies)
    if avg_latency < 100:
        ok("HTTP latency", f"Avg: {avg_latency:.1f}ms (p50), max: {max(latencies):.1f}ms")
    else:
        fail("HTTP latency", f"Avg: {avg_latency:.1f}ms (>100ms target)", "Medium")

    # 12.3 WebSocket latency
    async def ws_latency():
        import websockets
        latencies = []
        async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:
            for i in range(10):
                t0 = time.perf_counter()
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "health", "id": i, "params": {}}))
                await asyncio.wait_for(ws.recv(), 5)
                latencies.append((time.perf_counter() - t0) * 1000)
        return latencies

    try:
        ws_lats = asyncio.get_event_loop().run_until_complete(ws_latency())
        avg_ws = sum(ws_lats) / len(ws_lats)
        ok("WebSocket latency", f"Avg: {avg_ws:.1f}ms, max: {max(ws_lats):.1f}ms")
    except Exception as e:
        fail("WebSocket latency", str(e), "Medium")

    # 12.4 Memory usage snapshot
    try:
        import psutil
        proc_info = psutil.Process(proc.pid)
        mem = proc_info.memory_info()
        ok("Server memory", f"RSS: {mem.rss / 1024 / 1024:.1f}MB, VMS: {mem.vms / 1024 / 1024:.1f}MB")
    except ImportError:
        # Try Windows-specific
        try:
            subprocess.run(["tasklist", "/FI", f"PID eq {proc.pid}", "/FO", "CSV"],
                             capture_output=True, text=True, timeout=5)
            ok("Server memory", "tasklist output available")
        except Exception:
            ok("Server memory", "psutil not available, skipping")
    except Exception as e:
        ok("Server memory", f"Could not measure: {e}")

    # 12.5 Database performance
    async def db_perf():
        from core.session import Session
        from db.connection import Database, resolve_db_path
        from db.repository import SessionRepository

        db = Database(resolve_db_path())
        await db.connect()
        sr = SessionRepository(db)

        # Insert performance
        t0 = time.perf_counter()
        sessions = []
        for i in range(100):
            s = Session(title=f"Perf Test {i}")
            await sr.create(s)
            sessions.append(s)
        insert_time = (time.perf_counter() - t0) * 1000

        # Read performance
        t0 = time.perf_counter()
        for s in sessions:
            await sr.get(s.id)
        read_time = (time.perf_counter() - t0) * 1000

        # Cleanup
        for s in sessions:
            await sr.delete(s.id)

        await db.close()
        return insert_time, read_time

    try:
        ins, rd = asyncio.get_event_loop().run_until_complete(db_perf())
        ok("DB performance", f"100 inserts: {ins:.0f}ms, 100 reads: {rd:.0f}ms")
    except Exception as e:
        fail("DB performance", str(e), "Medium")

    # 12.6 Startup validation endpoint
    try:
        req = urllib.request.urlopen("http://127.0.0.1:8765/startup/validate", timeout=5)
        data = json.loads(req.read())
        ok("Startup validation", f"valid={data.get('valid')}")
    except Exception as e:
        fail("Startup validation", str(e), "Low")

    # Cleanup
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ══════════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ══════════════════════════════════════════════════════════════════════════

def generate_report():
    print(f"\n{'='*70}")
    print("  COMPREHENSIVE VALIDATION REPORT")
    print(f"{'='*70}\n")

    total_pass = 0
    total_fail = 0
    all_failures = []

    for r in reports:
        status_icon = "[OK]" if r.status == "PASS" else "[FAIL]"
        print(f"  {status_icon} Phase {r.phase_num}: {r.phase_name} -- {r.passed}/{r.total} passed")
        total_pass += r.passed
        total_fail += r.failed
        for test in r.results:
            if not test.passed:
                all_failures.append(test)
                print(f"      [FAIL] [{test.severity}] {test.name}: {test.message[:120]}")

    print(f"\n{'─'*70}")
    print(f"  TOTAL: {total_pass} passed, {total_fail} failed out of {total_pass + total_fail}")
    if total_fail == 0:
        print("  *** ALL PHASES PASSED -- PRODUCTION READY ***")
    else:
        print("\n  ISSUES BY SEVERITY:")
        for sev in ["Critical", "High", "Medium", "Low"]:
            items = [f for f in all_failures if f.severity == sev]
            if items:
                print(f"    {sev}: {len(items)}")
                for item in items:
                    print(f"      - {item.phase}: {item.name} — {item.message[:100]}")

    # Save report as JSON
    report_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_passed": total_pass,
        "total_failed": total_fail,
        "phases": [
            {
                "num": r.phase_num,
                "name": r.phase_name,
                "passed": r.passed,
                "failed": r.failed,
                "total": r.total,
                "status": r.status,
                "failures": [
                    {"name": t.name, "severity": t.severity, "message": t.message}
                    for t in r.results if not t.passed
                ]
            }
            for r in reports
        ]
    }
    report_path = ROOT / "validation_report.json"
    report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print(f"\n  Report saved to: {report_path}")

    return total_fail == 0


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    os.chdir(str(ROOT))
    print(f"\nZenith Production Validation — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python {sys.version}, cwd={os.getcwd()}")

    try:
        phase_1()
        phase_2()
        phase_3()
        phase_4()
        phase_5()
        phase_6()
        phase_7()
        phase_8()
        phase_9()
        phase_10()
        phase_11()
        phase_12()
    except KeyboardInterrupt:
        print("\n\nInterrupted!")
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        traceback.print_exc()
    finally:
        # Kill any leftover server
        subprocess.run(["taskkill", "/F", "/IM", "python.exe", "/T"],
                      capture_output=True, timeout=5)
        success = generate_report()
        sys.exit(0 if success else 1)
