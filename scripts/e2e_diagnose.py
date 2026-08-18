"""
Diagnostic harness: starts the backend, connects via WebSocket,
sends a prompt, logs every event, and analyses discrepancies.

Usage:
    python scripts/e2e_diagnose.py
    python scripts/e2e_diagnose.py --prompt "explain async/await in python"
    python scripts/e2e_diagnose.py --timeout 120
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8765
WS_URL = f"ws://{BACKEND_HOST}:{BACKEND_PORT}/ws"
STARTUP_TIMEOUT = 30  # seconds to wait for the backend to become ready
DEFAULT_PROMPT = (
    "Hey Zenith, can you give me the SOLID principles explained "
    "with a FastAPI example? Just explain, don't create any files."
)
LOG_DIR = REPO_ROOT / "scripts" / "e2e_logs"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class EventCollector:
    """Collects and categorises all WebSocket messages."""

    def __init__(self) -> None:
        self.all_messages: list[dict] = []
        self.rpc_responses: list[dict] = []
        self.events: list[dict] = []
        self.errors: list[dict] = []
        self.warnings: list[dict] = []
        self.event_kinds: list[str] = []
        self.start_time: float = time.monotonic()
        self.end_time: float | None = None

    def record(self, msg: dict) -> None:
        elapsed = time.monotonic() - self.start_time
        msg["_elapsed_s"] = round(elapsed, 3)
        self.all_messages.append(msg)

        if msg.get("method") == "event":
            self.events.append(msg)
            kind = msg.get("params", {}).get("kind", "unknown")
            self.event_kinds.append(kind)
            if kind == "error":
                self.errors.append(msg)
            elif kind == "warning":
                self.warnings.append(msg)
        elif "result" in msg or "error" in msg:
            self.rpc_responses.append(msg)

    def finish(self) -> None:
        self.end_time = time.monotonic()

    @property
    def duration_s(self) -> float:
        end = self.end_time or time.monotonic()
        return round(end - self.start_time, 3)


def _pp(obj: object, max_str: int = 500) -> str:
    """Pretty-print with truncation for long strings."""
    text = json.dumps(obj, indent=2, default=str)
    if len(text) > max_str * 3:
        lines = text.split("\n")
        truncated = "\n".join(lines[:40])
        return f"{truncated}\n... ({len(text)} chars total, truncated)"
    return text


# ---------------------------------------------------------------------------
# Backend lifecycle
# ---------------------------------------------------------------------------
async def wait_for_backend(host: str, port: int, timeout: float) -> bool:
    """Poll /health until the backend is ready."""
    import urllib.request

    url = f"http://{host}:{port}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read())
                    logging.info("Backend ready: %s", json.dumps(data, indent=2))
                    return True
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return False


def start_backend() -> subprocess.Popen:
    """Start the backend server as a subprocess."""
    logging.info("Starting backend: python -m server.main serve")
    env = os.environ.copy()
    backend_log = LOG_DIR / "backend_stdout.log"
    log_fh = open(backend_log, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "server.main", "serve"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    logging.info("Backend PID: %d (logs to %s)", proc.pid, backend_log)
    return proc


# ---------------------------------------------------------------------------
# WebSocket client
# ---------------------------------------------------------------------------
async def run_session(ws_url: str, prompt: str, timeout: float) -> EventCollector:
    """Connect to the backend WS, create a session, send a prompt, collect events."""
    import websockets

    collector = EventCollector()
    rpc_counter = 0

    logging.info("Connecting to %s", ws_url)
    async with websockets.connect(ws_url, max_size=2**22) as ws:
        logging.info("WebSocket connected")

        # --- 1. session.create ---
        rpc_counter += 1
        create_msg = {
            "jsonrpc": "2.0",
            "id": f"rpc_{rpc_counter}",
            "method": "session.create",
            "params": {
                "title": "E2E Diagnostic Session",
                "mode": "build",
            },
        }
        logging.info(">>> session.create (id=%s)", create_msg["id"])
        await ws.send(json.dumps(create_msg))

        session_id: str | None = None
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            msg = json.loads(raw)
            collector.record(msg)
            logging.info("<<< %s", _pp(msg, 300))

            if msg.get("id") == create_msg["id"]:
                result = msg.get("result", {})
                session_id = result.get("id")
                logging.info("Session created: %s", session_id)
                break

        if not session_id:
            logging.error("Failed to create session — aborting")
            return collector

        # Drain any remaining events for a moment
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                msg = json.loads(raw)
                collector.record(msg)
                logging.info("<<< (drain) %s", _pp(msg, 200))
        except (asyncio.TimeoutError, Exception):
            pass

        # --- 2. prompt.send ---
        rpc_counter += 1
        prompt_msg = {
            "jsonrpc": "2.0",
            "id": f"rpc_{rpc_counter}",
            "method": "prompt.send",
            "params": {
                "content": prompt,
                "mode": "build",
                "session_id": session_id,
            },
        }
        logging.info(">>> prompt.send (id=%s, prompt=%r)", create_msg["id"], prompt[:80])
        await ws.send(json.dumps(prompt_msg))

        # --- 3. Collect events until success or timeout ---
        prompt_deadline = time.monotonic() + timeout
        full_text_parts: list[str] = []

        while time.monotonic() < prompt_deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
            except asyncio.TimeoutError:
                logging.warning(
                    "Timeout waiting for next event (elapsed %.1fs)", collector.duration_s
                )
                break

            msg = json.loads(raw)
            collector.record(msg)

            kind = msg.get("params", {}).get("kind", "")
            data = msg.get("params", {}).get("data", {})

            if kind == "message":
                text = data.get("text", "")
                partial = data.get("partial", False)
                if text:
                    full_text_parts.append(text)
                    if not partial:
                        logging.info("<<< MESSAGE (complete): %s", text[:200])
                    else:
                        logging.debug("<<< MESSAGE (partial): %s", text[:100])
            elif kind == "thinking":
                logging.info("<<< THINKING: %s", str(data.get("text", ""))[:200])
            elif kind == "tool_call":
                logging.info(
                    "<<< TOOL_CALL: %s | params=%s",
                    data.get("tool", "?"),
                    _pp(data.get("params", {}), 200),
                )
            elif kind == "tool_result":
                output_preview = str(data.get("output", ""))[:200]
                logging.info(
                    "<<< TOOL_RESULT: %s | success=%s | output=%s",
                    data.get("tool", "?"),
                    data.get("success"),
                    output_preview,
                )
            elif kind == "success":
                logging.info("<<< SUCCESS: %s", _pp(data, 400))
                break
            elif kind == "error":
                logging.error("<<< ERROR EVENT: %s", _pp(data, 400))
                break
            else:
                logging.info("<<< EVENT[%s]: %s", kind, _pp(data, 200))

        collector.finish()

        # Log the assembled text
        full_text = "".join(full_text_parts)
        logging.info("=" * 60)
        logging.info("ASSEMBLED AGENT RESPONSE (%d chars):", len(full_text))
        logging.info(full_text)
        logging.info("=" * 60)

        return collector


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def analyse(collector: EventCollector, prompt: str) -> dict:
    """Analyse the collected events for discrepancies and quality issues."""
    report: dict = {
        "total_messages": len(collector.all_messages),
        "total_events": len(collector.events),
        "total_rpc_responses": len(collector.rpc_responses),
        "event_kinds_seen": collector.event_kinds,
        "errors": len(collector.errors),
        "warnings": len(collector.warnings),
        "duration_s": collector.duration_s,
        "got_success": "success" in collector.event_kinds,
    }

    issues: list[str] = []

    # Check: did we get a session.create response?
    create_responses = [r for r in collector.rpc_responses if r.get("id", "").startswith("rpc_")]
    if not create_responses:
        issues.append("No RPC response received for session.create")

    # Check: did we get a prompt.send ack?
    prompt_ack = None
    for r in collector.rpc_responses:
        result = r.get("result", {})
        if isinstance(result, dict) and result.get("status") == "processing":
            prompt_ack = r
            break
    if not prompt_ack:
        issues.append("No prompt.send acknowledgement (status=processing) received")

    # Check: did we get a success event?
    if "success" not in collector.event_kinds:
        issues.append("No 'success' event received — prompt may have timed out or errored")

    # Check: did we get an error event?
    if collector.errors:
        for err in collector.errors:
            err_data = err.get("params", {}).get("data", {})
            issues.append(f"Error event: {err_data.get('message', 'unknown')}")

    # Check: did we get thinking/message/tool_call events?
    expected_kinds = {"thinking", "message"}
    seen = set(collector.event_kinds)
    missing = expected_kinds - seen
    if missing:
        issues.append(f"Missing expected event kinds: {missing}")

    # Check: tool calls without tool results?
    tool_calls = [k for k in collector.event_kinds if k == "tool_call"]
    tool_results = [k for k in collector.event_kinds if k == "tool_result"]
    if len(tool_calls) != len(tool_results):
        issues.append(
            f"Tool call/result mismatch: {len(tool_calls)} calls vs {len(tool_results)} results"
        )

    # Check: were there context compaction events?
    if "context_compacted" in collector.event_kinds:
        issues.append(
            "Context compaction occurred during a single prompt — may indicate budget issue"
        )

    # Check: streaming messages — did partials arrive?
    partial_msgs = [
        e
        for e in collector.events
        if e.get("params", {}).get("kind") == "message"
        and e.get("params", {}).get("data", {}).get("partial")
    ]
    full_msgs = [
        e
        for e in collector.events
        if e.get("params", {}).get("kind") == "message"
        and not e.get("params", {}).get("data", {}).get("partial")
    ]
    report["partial_message_count"] = len(partial_msgs)
    report["full_message_count"] = len(full_msgs)
    if not partial_msgs and full_msgs:
        issues.append("No partial messages received — streaming may not be working")

    # Check: latency
    if collector.duration_s > 60:
        issues.append(f"Total duration {collector.duration_s}s exceeds 60s — very slow response")

    report["issues"] = issues
    report["issue_count"] = len(issues)
    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main(prompt: str, timeout: float) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"diagnose_{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logging.info("=" * 70)
    logging.info("E2E DIAGNOSTIC RUN — %s", timestamp)
    logging.info("Prompt: %s", prompt)
    logging.info("Timeout: %ss", timeout)
    logging.info("Log file: %s", log_file)
    logging.info("=" * 70)

    # Start backend
    backend_proc = start_backend()
    try:
        logging.info("Waiting for backend to start...")
        ready = await wait_for_backend(BACKEND_HOST, BACKEND_PORT, timeout)
        if not ready:
            logging.error("Backend failed to start within %ds", STARTUP_TIMEOUT)
            return 1

        # Run the session
        collector = await run_session(WS_URL, prompt, timeout)

        # Analyse
        report = analyse(collector, prompt)

        # Save report
        report_file = LOG_DIR / f"report_{timestamp}.json"
        report_file.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

        # Print summary
        logging.info("")
        logging.info("=" * 70)
        logging.info("DIAGNOSTIC REPORT")
        logging.info("=" * 70)
        logging.info("Total messages:   %d", report["total_messages"])
        logging.info("Total events:     %d", report["total_events"])
        logging.info("Event kinds seen: %s", report["event_kinds_seen"])
        logging.info("Duration:         %.1fs", report["duration_s"])
        logging.info("Got success:      %s", report["got_success"])
        logging.info("Partial messages: %d", report["partial_message_count"])
        logging.info("Full messages:    %d", report["full_message_count"])
        logging.info(
            "Tool calls:       %d", sum(1 for k in report["event_kinds_seen"] if k == "tool_call")
        )
        logging.info(
            "Tool results:     %d", sum(1 for k in report["event_kinds_seen"] if k == "tool_result")
        )
        logging.info("Errors:           %d", report["errors"])
        logging.info("Warnings:         %d", report["warnings"])
        logging.info("")
        if report["issues"]:
            logging.warning("ISSUES FOUND (%d):", report["issue_count"])
            for i, issue in enumerate(report["issues"], 1):
                logging.warning("  %d. %s", i, issue)
        else:
            logging.info("NO ISSUES — everything looks healthy!")
        logging.info("")
        logging.info("Report saved: %s", report_file)
        logging.info("Full log:     %s", log_file)
        logging.info("=" * 70)

        return 0 if not report["issues"] else 1

    finally:
        logging.info("Shutting down backend (PID %d)...", backend_proc.pid)
        try:
            backend_proc.terminate()
            backend_proc.wait(timeout=5)
        except Exception:
            backend_proc.kill()
        logging.info("Backend stopped")


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="E2E diagnostic for Zenith backend+frontend protocol"
    )
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Prompt to send")
    parser.add_argument("--timeout", type=float, default=90, help="Timeout in seconds")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.prompt, args.timeout)))


if __name__ == "__main__":
    cli()
