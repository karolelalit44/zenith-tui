"""
E2E Context & Session Persistence Test — Part 1

Creates a fresh session, sends 3 prompts in sequence, and logs:
  - What is sent to the model (inferred from persisted messages on resume)
  - What the model responds with (captured from WS events)
  - Session state at each step

Outputs:
  - Plain-text log file  (e2e_context_log.txt, next to this script)
  - Session ID file       (e2e_session_id.txt) for Part 2 to resume

Usage:
  python server/tests/test_context_session_e2e_part1.py
  (server must already be running on ws://127.0.0.1:8765/ws)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import websockets  # noqa: E402

WS_URL = os.environ.get("ZENITH_WS_URL", "ws://127.0.0.1:8765/ws")
SCRIPT_DIR = Path(__file__).resolve().parent
# E2E run artifacts belong outside the source tree (gitignored scratch area).
LOG_DIR = SCRIPT_DIR.parent.parent / "scripts" / "e2e_logs"
LOG_FILE = LOG_DIR / "e2e_context_log.txt"
SESSION_ID_FILE = LOG_DIR / "e2e_session_id.txt"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── helpers ──────────────────────────────────────────────────────────────────

_rpc_id = 0


def next_id() -> str:
    global _rpc_id
    _rpc_id += 1
    return f"e2e_{_rpc_id}"


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def divider(title: str) -> str:
    return f"\n{'=' * 80}\n  {title}\n{'=' * 80}"


class Log:
    """Append-only plain-text log writer."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.write_text("", encoding="utf-8")

    def write(self, text: str) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
        print(text, flush=True)


# ── WS helpers ───────────────────────────────────────────────────────────────


async def ws_rpc(ws, method: str, params: dict | None = None) -> dict:
    rid = next_id()
    req: dict = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params:
        req["params"] = params
    await ws.send(json.dumps(req))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=30)
        data = json.loads(raw)
        if "id" in data and data["id"] == rid:
            return data
        # skip pings / events that arrived between sends
        if data.get("method") == "ping":
            continue


async def ws_collect_events(ws, timeout: float = 60) -> list[dict]:
    events: list[dict] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = deadline - time.time()
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, remaining))
        except (TimeoutError, asyncio.TimeoutError):
            break
        data = json.loads(raw)
        if data.get("method") == "ping":
            continue
        if data.get("method") == "event":
            events.append(data["params"])
            if data["params"].get("kind") in ("success", "error"):
                break
    return events


def format_assistant_text(events: list[dict]) -> str:
    parts = []
    for e in events:
        if e.get("kind") == "message" and not e.get("data", {}).get("partial"):
            text = e.get("data", {}).get("text", "")
            if text:
                parts.append(text)
    return "\n".join(parts)


def format_events_summary(events: list[dict]) -> str:
    lines = []
    for i, e in enumerate(events):
        kind = e.get("kind", "?")
        data = e.get("data", {})
        if kind == "thinking":
            preview = (data.get("text", "") or "")[:200]
            lines.append(
                f"  [{i:2d}] THINKING  {preview}{'...' if len(data.get('text', '')) > 200 else ''}"
            )
        elif kind == "message":
            partial = " (partial)" if data.get("partial") else ""
            preview = (data.get("text", "") or "")[:200]
            lines.append(
                f"  [{i:2d}] MESSAGE{partial}  iter={data.get('iteration', '?')}  {preview}{'...' if len(data.get('text', '')) > 200 else ''}"
            )
        elif kind == "tool_call":
            lines.append(
                f"  [{i:2d}] TOOL_CALL  tool={data.get('tool', '?')}  params={json.dumps(data.get('params', {}))[:120]}"
            )
        elif kind == "tool_result":
            out = str(data.get("output", ""))
            lines.append(
                f"  [{i:2d}] TOOL_RESULT  tool={data.get('tool', '?')}  success={data.get('success')}  output_len={len(out)}"
            )
        elif kind == "success":
            lines.append(
                f"  [{i:2d}] SUCCESS  iterations={data.get('iterations')}  elapsed={data.get('elapsedMs', data.get('duration', '?'))}ms  tokens={json.dumps(data.get('tokenInfo', {}))[:120]}"
            )
        elif kind == "error":
            lines.append(
                f"  [{i:2d}] ERROR  {data.get('message', '')}  code={data.get('code', '?')}  hint={data.get('hint', '')}"
            )
        elif kind == "warning":
            lines.append(f"  [{i:2d}] WARNING  {data.get('message', '')}")
        elif kind == "turn_manifest":
            manifest = data.get("manifest", data)
            lines.append(
                f"  [{i:2d}] TURN_MANIFEST  created={manifest.get('created', [])}  modified={manifest.get('modified', [])}  verified={manifest.get('verified')}"
            )
        elif kind in (
            "context_compaction_started",
            "context_compaction_phase",
            "context_compaction_ended",
        ):
            lines.append(f"  [{i:2d}] {kind.upper()}  {json.dumps(data)[:160]}")
        elif kind == "session_initialized":
            lines.append(f"  [{i:2d}] SESSION_INITIALIZED  session={data.get('session_id', '?')}")
        else:
            lines.append(f"  [{i:2d}] {kind.upper()}  {json.dumps(data)[:160]}")
    return "\n".join(lines)


def format_persisted_messages(messages: list[dict]) -> str:
    lines = []
    for i, m in enumerate(messages):
        role = m.get("role", "?")
        content = m.get("content", "")
        meta = m.get("metadata", {})
        token_count = m.get("token_count", 0)
        created = m.get("created_at", "")
        preview = content[:500].replace("\n", "\\n") if content else "(empty)"
        suffix = ""
        if meta:
            suffix = f"  meta={json.dumps(meta)[:100]}"
        lines.append(
            f"  [{i:2d}] role={role:10s} tokens={token_count:5d}  created={created}  content_len={len(content)}{suffix}"
        )
        lines.append(f"       preview: {preview}")
    return "\n".join(lines)


# ── main test ────────────────────────────────────────────────────────────────

PROMPTS = [
    {
        "number": 1,
        "content": "My project name is Zenith and it is a coding agent server built with Python. "
        "The main entry point is server/main.py. Please confirm you understand.",
        "mode": "build",
        "description": "First message — establishes facts the model must remember",
    },
    {
        "number": 2,
        "content": "Based on what I told you earlier, what is the project name and where is the main entry point?",
        "mode": "build",
        "description": "Second message — depends on context from first (tests context carry-over)",
    },
    {
        "number": 3,
        "content": "Say just the word 'ok' to confirm you still have context.",
        "mode": "build",
        "description": "Third message — simple follow-up, verifies context still present",
    },
]


async def run_part1() -> str:
    log = Log(LOG_FILE)
    log.write(divider("E2E CONTEXT & SESSION PERSISTENCE TEST — PART 1"))
    log.write(f"Started: {ts()}")
    log.write(f"WebSocket: {WS_URL}")
    log.write(f"Log file: {LOG_FILE}")

    session_id: str | None = None

    async with websockets.connect(WS_URL) as ws:
        log.write(f"WebSocket connected: {WS_URL}")

        # ── Create session ───────────────────────────────────────────────
        log.write(divider("STEP 1: CREATE SESSION"))
        resp = await ws_rpc(ws, "session.create", {"title": f"E2E Context Test {ts()}"})
        assert "result" in resp, f"session.create failed: {resp}"
        session_id = resp["result"]["id"]
        log.write(f"Session created: {session_id}")
        log.write(f"Session data: {json.dumps(resp['result'], indent=2)[:600]}")

        # ── Send prompts ─────────────────────────────────────────────────
        for prompt_cfg in PROMPTS:
            num = prompt_cfg["number"]
            content = prompt_cfg["content"]
            mode = prompt_cfg["mode"]
            desc = prompt_cfg["description"]

            log.write(divider(f"PROMPT #{num}: {desc}"))
            log.write(f"Timestamp: {ts()}")
            log.write(f"Session ID: {session_id}")
            log.write(f"Mode: {mode}")
            log.write(f"Content ({len(content)} chars):")
            log.write(f"  {content}")

            # Send prompt
            t0 = time.monotonic()
            prompt_resp = await ws_rpc(
                ws,
                "prompt.send",
                {
                    "content": content,
                    "mode": mode,
                    "session_id": session_id,
                },
            )
            log.write(f"\nPrompt accepted: {json.dumps(prompt_resp.get('result', {}))}")

            # Collect events
            events = await ws_collect_events(ws, timeout=90)
            elapsed = time.monotonic() - t0

            log.write(f"\nEvents received: {len(events)} total ({elapsed:.1f}s wall time)")
            log.write("Event timeline:")
            log.write(format_events_summary(events))

            # Extract assistant response
            assistant_text = format_assistant_text(events)
            log.write(f"\nAssistant response ({len(assistant_text)} chars):")
            log.write(f"  {assistant_text[:1000]}{'...' if len(assistant_text) > 1000 else ''}")

            # Check for errors
            error_events = [e for e in events if e.get("kind") == "error"]
            if error_events:
                log.write("\n*** ERRORS DETECTED ***")
                for err in error_events:
                    log.write(
                        f"  {err.get('data', {}).get('message', '')}  code={err.get('data', {}).get('code', '?')}"
                    )

            # Get success info
            success_events = [e for e in events if e.get("kind") == "success"]
            if success_events:
                se = success_events[0]
                ti = se.get("data", {}).get("tokenInfo", {})
                log.write(
                    f"\nToken info: prompt={ti.get('prompt_tokens', '?')}  "
                    f"completion={ti.get('completion_tokens', '?')}  "
                    f"cached={ti.get('cached_tokens', '?')}  "
                    f"total={ti.get('total', '?')}  "
                    f"estimated={ti.get('estimated', '?')}"
                )

            # Small delay between prompts to allow server to finish persisting
            if num < len(PROMPTS):
                log.write("\nWaiting 2s before next prompt...")
                await asyncio.sleep(2)

        # ── After all prompts: resume session to inspect persisted state ──
        log.write(divider("STEP 2: RESUME SESSION TO INSPECT PERSISTED STATE"))
        log.write("Re-opening the session via session.resume to see all persisted messages...")
        resume_resp = await ws_rpc(ws, "session.resume", {"session_id": session_id})
        if "result" in resume_resp:
            result = resume_resp["result"]
            messages = result.get("messages", [])
            log.write(f"\nSession resume returned {len(messages)} persisted messages:")
            log.write(format_persisted_messages(messages))

            # Check if old user messages are present
            user_msgs = [m for m in messages if m.get("role") == "user"]
            assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
            log.write(f"\nPersisted user messages: {len(user_msgs)}")
            log.write(f"Persisted assistant messages: {len(assistant_msgs)}")
            for i, um in enumerate(user_msgs):
                log.write(f"  User #{i + 1}: {um.get('content', '')[:200]}")
            for i, am in enumerate(assistant_msgs):
                log.write(f"  Assistant #{i + 1}: {am.get('content', '')[:200]}")

            # Check for session summary in metadata
            session_data = result.get("session", {})
            metadata = session_data.get("metadata", {})
            if metadata.get("summary"):
                log.write(f"\nSession summary persisted ({len(metadata['summary'])} chars):")
                log.write(
                    f"  {metadata['summary'][:500]}{'...' if len(metadata.get('summary', '')) > 500 else ''}"
                )
            else:
                log.write(
                    f"\nNo session summary persisted yet (metadata keys: {list(metadata.keys())})"
                )
        else:
            log.write(f"\n*** session.resume FAILED: {resume_resp} ***")

    # ── Write session ID for Part 2 ──────────────────────────────────────
    SESSION_ID_FILE.write_text(session_id, encoding="utf-8")
    log.write(divider("PART 1 COMPLETE"))
    log.write(f"Session ID written to: {SESSION_ID_FILE}")
    log.write(f"Session ID: {session_id}")
    log.write(f"Log file: {LOG_FILE}")
    log.write(f"Finished: {ts()}")
    return session_id


if __name__ == "__main__":
    sid = asyncio.run(run_part1())
    print(f"\nDone. Session ID: {sid}")
    print("Run Part 2 with:  python server/tests/test_context_session_e2e_part2.py")
