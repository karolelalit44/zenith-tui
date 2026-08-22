"""
Comprehensive E2E test: covers every RPC method and event kind the TUI frontend uses.
Starts the backend, runs all operations, and reports discrepancies.

Usage:
    python scripts/e2e_comprehensive.py
    python scripts/e2e_comprehensive.py --timeout 120
    python scripts/e2e_comprehensive.py --skip-prompt   # skip prompt.send (faster, no LLM call)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8765
WS_URL = f"ws://{BACKEND_HOST}:{BACKEND_PORT}/ws"
LOG_DIR = REPO_ROOT / "scripts" / "e2e_logs"
LOG_FORMAT = "%(asctime)s [%(levelname)-7s] %(message)s"


def _safe_str(obj) -> str:
    """Encode to str safely on Windows cp1252 consoles."""
    s = str(obj)
    try:
        s.encode("cp1252")
        return s
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s.encode("ascii", errors="replace").decode()


class RPCClient:
    """Minimal JSON-RPC 2.0 WebSocket client for testing."""

    def __init__(self, ws):
        self._ws = ws
        self._counter = 0
        self._pending: dict[str, asyncio.Future] = {}
        self.events: list[dict] = []
        self.event_kinds: list[str] = []
        self._all_received: list[dict] = []
        self._receiver_task: asyncio.Task | None = None

    async def start_receiver(self):
        self._receiver_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self):
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                self._all_received.append(msg)
                if msg.get("method") == "event":
                    kind = msg.get("params", {}).get("kind", "unknown")
                    self.events.append(msg)
                    self.event_kinds.append(kind)
                elif "id" in msg and msg["id"] in self._pending:
                    self._pending[msg["id"]].set_result(msg)
        except Exception:
            pass

    async def call(self, method: str, params: dict | None = None, timeout: float = 15) -> dict:
        self._counter += 1
        rid = f"rpc_{self._counter}"
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params:
            msg["params"] = params
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut
        await self._ws.send(json.dumps(msg))
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            return {"error": {"message": f"Timeout after {timeout}s", "code": -1}}
        finally:
            self._pending.pop(rid, None)

    async def wait_for_event(self, kind: str, timeout: float = 30) -> dict | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for i, ev in enumerate(self.events):
                if ev.get("params", {}).get("kind") == kind:
                    return ev
            remaining = deadline - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(0.1)
        return None

    async def drain_events(self, duration: float = 2.0) -> list[dict]:
        """Collect events for a fixed duration."""
        collected = []
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        collected = [e for e in self.events]
        return collected

    async def close(self):
        if self._receiver_task:
            self._receiver_task.cancel()
            try:
                await self._receiver_task
            except asyncio.CancelledError:
                pass


class TestResult:
    def __init__(self):
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.skipped: list[str] = []
        self.warnings: list[str] = []

    def ok(self, name: str):
        self.passed.append(name)
        logging.info("  PASS  %s", name)

    def fail(self, name: str, reason: str):
        self.failed.append(f"{name}: {reason}")
        logging.error("  FAIL  %s -- %s", name, _safe_str(reason))

    def skip(self, name: str, reason: str = ""):
        self.skipped.append(f"{name}: {reason}" if reason else name)
        logging.warning("  SKIP  %s%s", name, f" — {reason}" if reason else "")

    def warn(self, name: str, msg: str):
        self.warnings.append(f"{name}: {msg}")
        logging.warning("  WARN  %s -- %s", name, _safe_str(msg))

    def summary(self) -> str:
        lines = [
            "",
            "=" * 70,
            "COMPREHENSIVE TEST RESULTS",
            "=" * 70,
            f"  Passed:   {len(self.passed)}",
            f"  Failed:   {len(self.failed)}",
            f"  Skipped:  {len(self.skipped)}",
            f"  Warnings: {len(self.warnings)}",
            "",
        ]
        if self.failed:
            lines.append("FAILURES:")
            for f in self.failed:
                lines.append(f"  - {_safe_str(f)}")
            lines.append("")
        if self.warnings:
            lines.append("WARNINGS:")
            for w in self.warnings:
                lines.append(f"  - {_safe_str(w)}")
            lines.append("")
        if self.skipped:
            lines.append("SKIPPED:")
            for s in self.skipped:
                lines.append(f"  - {_safe_str(s)}")
            lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Backend lifecycle
# ---------------------------------------------------------------------------
def start_backend() -> subprocess.Popen:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_fh = open(LOG_DIR / "backend_comprehensive.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "server.main", "serve"],
        cwd=str(REPO_ROOT),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    logging.info("Backend started: PID %d", proc.pid)
    return proc


async def wait_for_backend(timeout: float) -> bool:
    import urllib.request

    url = f"http://{BACKEND_HOST}:{BACKEND_PORT}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
async def test_health(r: TestResult, client: RPCClient):
    """Test /health endpoint."""
    import urllib.request

    try:
        req = urllib.request.Request(f"http://{BACKEND_HOST}:{BACKEND_PORT}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            if data.get("status") == "ok":
                r.ok("health_endpoint")
            else:
                r.fail("health_endpoint", f"Unexpected: {data}")
    except Exception as e:
        r.fail("health_endpoint", str(e))


async def test_status(r: TestResult):
    """Test /status endpoint."""
    import urllib.request

    try:
        req = urllib.request.Request(f"http://{BACKEND_HOST}:{BACKEND_PORT}/status")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            if isinstance(data, dict) and len(data) >= 3:
                r.ok("status_endpoint")
            else:
                r.fail("status_endpoint", f"Unexpected: {type(data)}")
    except Exception as e:
        r.fail("status_endpoint", str(e))


async def test_session_crud(r: TestResult, client: RPCClient):
    """Test session.create, session.list, session.list_all, session.resume, session.update, session.delete."""
    # create
    resp = await client.call("session.create", {"title": "Test CRUD Session"})
    result = resp.get("result", {})
    session_id = result.get("id")
    if not session_id:
        r.fail("session.create", f"No session id: {resp}")
        return
    r.ok("session.create")

    # list_all
    resp = await client.call("session.list_all", {"limit": 10})
    result = resp.get("result", resp)
    if isinstance(result, list):
        r.ok(f"session.list_all ({len(result)} sessions)")
    elif isinstance(result, dict) and "sessions" in result:
        r.ok(f"session.list_all ({len(result['sessions'])} sessions)")
    elif not resp.get("error"):
        r.ok("session.list_all (empty)")
    else:
        r.fail("session.list_all", str(resp.get("error")))

    # update
    resp = await client.call("session.update", {"session_id": session_id, "title": "Updated Title"})
    if resp.get("result") and not resp.get("error"):
        r.ok("session.update")
    else:
        r.fail("session.update", str(resp))

    # resume
    resp = await client.call("session.resume", {"session_id": session_id})
    if resp.get("result"):
        r.ok("session.resume")
    else:
        r.fail("session.resume", str(resp))

    # delete
    resp = await client.call("session.delete", {"session_id": session_id})
    if not resp.get("error"):
        r.ok("session.delete")
    else:
        r.fail("session.delete", str(resp.get("error")))


async def test_session_advanced(r: TestResult, client: RPCClient):
    """Test session.pause, session.archive, session.checkpoint, session.duplicate, session.export."""
    # Create a session
    resp = await client.call("session.create", {"title": "Advanced Ops"})
    sid = resp.get("result", {}).get("id")
    if not sid:
        r.fail("session.advanced.create", "No session id")
        return

    # resume → RESUMED
    resp = await client.call("session.resume", {"session_id": sid})
    if not resp.get("error"):
        r.ok("session.resume_to_resumed")
    else:
        r.fail("session.resume_to_resumed", str(resp.get("error")))

    # Send a prompt to transition → ACTIVE (pause requires active state)
    client.events.clear()
    resp = await client.call(
        "prompt.send",
        {"content": "ok", "mode": "build", "session_id": sid},
        timeout=60,
    )
    if resp.get("result", {}).get("status") == "processing":
        r.ok("session.advanced.activate_via_prompt")
    else:
        r.fail("session.advanced.activate_via_prompt", f"Unexpected: {resp}")
        return

    # Wait for success (→ ACTIVE)
    terminal = await client.wait_for_event("success", timeout=60)
    if not terminal or terminal.get("params", {}).get("kind") != "success":
        r.fail("session.advanced.wait_for_active", "No success event")
        return
    r.ok("session.advanced.reached_active")

    # Now pause (requires ACTIVE)
    resp = await client.call("session.pause", {"session_id": sid})
    if not resp.get("error"):
        r.ok("session.pause")
    else:
        r.fail("session.pause", str(resp.get("error")))

    # resume back from paused → ACTIVE
    resp = await client.call("session.resume", {"session_id": sid})
    if not resp.get("error"):
        r.ok("session.resume_from_paused")
    else:
        r.fail("session.resume_from_paused", str(resp.get("error")))

    # checkpoint
    resp = await client.call("session.checkpoint", {"session_id": sid})
    if not resp.get("error"):
        r.ok("session.checkpoint")
    else:
        r.fail("session.checkpoint", str(resp.get("error")))

    # duplicate
    resp = await client.call("session.duplicate", {"session_id": sid, "title": "Dup"})
    result = resp.get("result", {})
    dup_id = result.get("id") if isinstance(result, dict) else None
    if dup_id:
        r.ok("session.duplicate")
        await client.call("session.delete", {"session_id": dup_id})
    elif not resp.get("error"):
        r.ok("session.duplicate (no id returned)")
    else:
        r.fail("session.duplicate", str(resp.get("error")))

    # archive
    resp = await client.call("session.archive", {"session_id": sid})
    if not resp.get("error"):
        r.ok("session.archive")
    else:
        r.fail("session.archive", str(resp.get("error")))

    # restore
    resp = await client.call("session.restore", {"session_id": sid})
    if not resp.get("error"):
        r.ok("session.restore")
    else:
        r.fail("session.restore", str(resp.get("error")))

    # export
    resp = await client.call("session.export", {"session_id": sid})
    if not resp.get("error"):
        r.ok("session.export")
    else:
        r.fail("session.export", str(resp.get("error")))

    # sync
    resp = await client.call("session.sync", {"session_id": sid, "since_sequence": 0})
    if not resp.get("error"):
        r.ok("session.sync")
    else:
        r.fail("session.sync", str(resp.get("error")))

    # search
    resp = await client.call("session.search", {"session_id": sid, "query": "test"})
    if not resp.get("error"):
        r.ok("session.search")
    else:
        r.fail("session.search", str(resp.get("error")))

    # clean up
    await client.call("session.delete", {"session_id": sid})


async def test_workspace_ops(r: TestResult, client: RPCClient):
    """Test workspace.status, workspace.diff, workspace.log."""
    resp = await client.call("workspace.status", {})
    if resp.get("result") or not resp.get("error"):
        r.ok("workspace.status")
    else:
        r.fail("workspace.status", str(resp.get("error")))

    resp = await client.call("workspace.diff", {})
    if resp.get("result") or not resp.get("error"):
        r.ok("workspace.diff")
    else:
        r.fail("workspace.diff", str(resp.get("error")))

    resp = await client.call("workspace.log", {"limit": 5})
    if resp.get("result") or not resp.get("error"):
        r.ok("workspace.log")
    else:
        r.fail("workspace.log", str(resp.get("error")))


async def test_provider_ops(r: TestResult, client: RPCClient):
    """Test provider.models, provider.validate."""
    resp = await client.call("provider.models", {"provider": "openrouter"})
    result = resp.get("result", {})
    if isinstance(result, dict) and ("models" in result or "model_ids" in result):
        r.ok("provider.models")
    elif not resp.get("error"):
        r.ok("provider.models (empty)")
    else:
        r.fail("provider.models", str(resp.get("error")))


async def test_tools_list(r: TestResult, client: RPCClient):
    """Test tools.list."""
    resp = await client.call("tools.list", {})
    result = resp.get("result", {})
    if isinstance(result, dict) and (
        "tools" in result or "schemas" in result or "tools" in str(result)
    ):
        r.ok("tools.list")
    elif not resp.get("error"):
        r.ok("tools.list (empty)")
    else:
        r.fail("tools.list", str(resp.get("error")))


async def test_memory_ops(r: TestResult, client: RPCClient):
    """Test memory.list, memory.add, memory.delete."""
    resp = await client.call("memory.list", {})
    if not resp.get("error"):
        r.ok("memory.list")
    else:
        r.fail("memory.list", str(resp.get("error")))

    resp = await client.call("memory.add", {"key": "test_key", "value": "test_value"})
    if not resp.get("error"):
        r.ok("memory.add")
    else:
        r.fail("memory.add", str(resp.get("error")))

    resp = await client.call("memory.delete", {"key": "test_key"})
    if not resp.get("error"):
        r.ok("memory.delete")
    else:
        r.fail("memory.delete", str(resp.get("error")))


async def test_context_compact(r: TestResult, client: RPCClient):
    """Test context.compact."""
    resp = await client.call("session.create", {"title": "Compact Test"})
    sid = resp.get("result", {}).get("id")
    if not sid:
        r.fail("context.compact.create", "No session id")
        return

    resp = await client.call("context.compact", {"session_id": sid})
    if not resp.get("error"):
        r.ok("context.compact")
    else:
        r.fail("context.compact", str(resp.get("error")))

    await client.call("session.delete", {"session_id": sid})


async def test_prompt_flow(r: TestResult, client: RPCClient, timeout: float):
    """Test prompt.send end-to-end with event verification."""
    # Create session
    resp = await client.call("session.create", {"title": "Prompt Flow Test"})
    sid = resp.get("result", {}).get("id")
    if not sid:
        r.fail("prompt.send.create", "No session id")
        return

    # Clear events from create
    client.events.clear()
    client.event_kinds.clear()

    # Send prompt
    resp = await client.call(
        "prompt.send",
        {"content": "Say hello in one sentence.", "mode": "build", "session_id": sid},
        timeout=60,
    )
    result = resp.get("result", {})
    if result.get("status") == "processing":
        r.ok("prompt.send.ack")
    else:
        r.fail("prompt.send.ack", f"Expected status=processing, got: {result}")

    # Wait for success or error
    terminal = await client.wait_for_event(
        "success", timeout=timeout
    ) or await client.wait_for_event("error", timeout=1)
    if terminal:
        kind = terminal.get("params", {}).get("kind", "")
        if kind == "success":
            data = terminal.get("params", {}).get("data", {})
            r.ok("prompt.send.success")
            logging.info(
                "    Token usage: prompt=%s completion=%s total=%s",
                data.get("tokenInfo", {}).get("prompt_tokens", "?"),
                data.get("tokenInfo", {}).get("completion_tokens", "?"),
                data.get("tokenInfo", {}).get("used", "?"),
            )
        elif kind == "error":
            r.fail("prompt.send.error", str(data := terminal.get("params", {}).get("data", {})))
    else:
        r.fail("prompt.send.timeout", "No success/error event received")

    # Verify event kinds the TUI expects
    seen = set(client.event_kinds)
    logging.info("    Event kinds seen: %s", sorted(seen))

    expected_wire_kinds = {"message", "success", "turn_manifest"}
    for kind in expected_wire_kinds:
        if kind in seen:
            r.ok(f"event_kind.{kind}")
        else:
            r.fail(f"event_kind.{kind}", f"Expected but not seen. Got: {sorted(seen)}")

    # Verify message streaming (partials)
    msgs = [e for e in client.events if e.get("params", {}).get("kind") == "message"]
    partials = [m for m in msgs if m.get("params", {}).get("data", {}).get("partial")]
    fulls = [m for m in msgs if not m.get("params", {}).get("data", {}).get("partial")]
    if partials:
        r.ok("message_streaming.partials")
    else:
        r.warn("message_streaming.partials", "No partial messages — streaming may not be working")
    if fulls:
        r.ok("message_streaming.final")
    else:
        r.fail("message_streaming.final", "No final (non-partial) message received")

    # Verify turn_manifest
    manifests = [e for e in client.events if e.get("params", {}).get("kind") == "turn_manifest"]
    if manifests:
        manifest_data = manifests[-1].get("params", {}).get("data", {})
        if "created" in manifest_data and "modified" in manifest_data:
            r.ok("turn_manifest.structure")
        else:
            r.fail("turn_manifest.structure", f"Missing fields: {list(manifest_data.keys())}")
    else:
        r.warn(
            "turn_manifest.structure",
            "No turn_manifest event (may be OK for pure-explanation prompts)",
        )

    # Verify success event structure
    if terminal and terminal.get("params", {}).get("kind") == "success":
        data = terminal.get("params", {}).get("data", {})
        required_fields = ["message", "iterations", "elapsedMs"]
        missing = [f for f in required_fields if f not in data]
        if not missing:
            r.ok("success_event.structure")
        else:
            r.fail("success_event.structure", f"Missing: {missing}")

        # tokenInfo
        ti = data.get("tokenInfo", {})
        ti_fields = ["used", "remaining", "total", "percent"]
        ti_missing = [f for f in ti_fields if f not in ti]
        if not ti_missing:
            r.ok("success_event.tokenInfo")
        else:
            r.fail("success_event.tokenInfo", f"Missing: {ti_missing}")

        # Check stale_reads_evicted (our new field)
        if "stale_reads_evicted" in data or "stale_reads_evicted" in ti:
            r.ok("success_event.stale_reads_evicted")
        else:
            r.warn(
                "success_event.stale_reads_evicted",
                "Field not in success data (check key location)",
            )

        # Check cache_hit_rate
        if "cache_hit_rate" in data or "cache_hit_rate" in ti:
            r.ok("success_event.cache_hit_rate")
        else:
            r.warn("success_event.cache_hit_rate", "Field not in success data (check key location)")

        # Check tierBreakdown
        tb = ti.get("tierBreakdown", data.get("tierBreakdown", {}))
        if tb:
            r.ok("success_event.tierBreakdown")
        else:
            r.warn("success_event.tierBreakdown", "No tier breakdown in success event")

    # Clean up
    await client.call("session.delete", {"session_id": sid})


async def test_event_kind_coverage(r: TestResult, client: RPCClient, skip_prompt: bool):
    """Check which event kinds the backend CAN emit vs what TUI expects."""
    TUI_EXPECTS = {
        "thinking",
        "message",
        "tool_call",
        "tool_result",
        "error",
        "warning",
        "success",
        "progress",
        "plan_ready",
        "context_compaction_started",
        "context_compacted",
        "context_compaction_ended",
        "context_compaction_phase",
        "agent_orchestration",
        "turn_manifest",
        "todo_board",
        "todo_test",
    }
    BACKEND_CAN_EMIT = {
        "thinking",
        "message",
        "tool_call",
        "tool_result",
        "error",
        "warning",
        "success",
        "progress",
        "plan_ready",
        "context_compaction_started",
        "context_compacted",
        "context_compaction_ended",
        "context_compaction_phase",
        "turn_manifest",
        "session_created",
        "session_state_changed",
        "token_usage_recorded",
        "token_budget_exceeded",
    }
    missing_from_backend = TUI_EXPECTS - BACKEND_CAN_EMIT
    if missing_from_backend:
        r.warn("event_kind_coverage", f"Backend cannot emit: {missing_from_backend}")
    else:
        r.ok("event_kind_coverage.backend_covers_tui")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main(timeout: float, skip_prompt: bool):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / "comprehensive.log", encoding="utf-8"),
        ],
    )

    r = TestResult()
    backend_proc = start_backend()

    try:
        logging.info("Waiting for backend...")
        if not await wait_for_backend(timeout):
            logging.error("Backend failed to start")
            return 1
        logging.info("Backend ready")

        import websockets

        async with websockets.connect(WS_URL, max_size=2**22) as ws:
            client = RPCClient(ws)
            await client.start_receiver()
            await asyncio.sleep(0.5)

            logging.info("")
            logging.info("--- HTTP ENDPOINTS ---")
            await test_health(r, client)
            await test_status(r)

            logging.info("")
            logging.info("--- SESSION CRUD ---")
            await test_session_crud(r, client)

            logging.info("")
            logging.info("--- SESSION ADVANCED ---")
            await test_session_advanced(r, client)

            logging.info("")
            logging.info("--- WORKSPACE OPS ---")
            await test_workspace_ops(r, client)

            logging.info("")
            logging.info("--- PROVIDER OPS ---")
            await test_provider_ops(r, client)

            logging.info("")
            logging.info("--- TOOLS ---")
            await test_tools_list(r, client)

            logging.info("")
            logging.info("--- MEMORY ---")
            await test_memory_ops(r, client)

            logging.info("")
            logging.info("--- CONTEXT COMPACT ---")
            await test_context_compact(r, client)

            logging.info("")
            logging.info("--- EVENT KIND COVERAGE ---")
            await test_event_kind_coverage(r, client, skip_prompt)

            if not skip_prompt:
                logging.info("")
                logging.info("--- PROMPT FLOW (LLM) ---")
                await test_prompt_flow(r, client, timeout)
            else:
                r.skip("prompt_flow", "Skipped via --skip-prompt")

            await client.close()

        # Print report
        summary = r.summary()
        logging.info(summary)

        # Save report
        report = {
            "passed": r.passed,
            "failed": r.failed,
            "skipped": r.skipped,
            "warnings": r.warnings,
            "total_pass": len(r.passed),
            "total_fail": len(r.failed),
            "total_skip": len(r.skipped),
            "total_warn": len(r.warnings),
        }
        report_file = LOG_DIR / f"comprehensive_report_{time.strftime('%Y%m%d_%H%M%S')}.json"
        report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        logging.info("Report saved: %s", report_file)

        return 1 if r.failed else 0

    finally:
        logging.info("Shutting down backend (PID %d)...", backend_proc.pid)
        try:
            backend_proc.terminate()
            backend_proc.wait(timeout=5)
        except Exception:
            backend_proc.kill()


def cli():
    parser = argparse.ArgumentParser(description="Comprehensive E2E test for Zenith")
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--skip-prompt", action="store_true", help="Skip prompt.send (no LLM call)")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.timeout, args.skip_prompt)))


if __name__ == "__main__":
    cli()
