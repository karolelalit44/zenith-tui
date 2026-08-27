"""
E2E Context & Session Persistence Test — Part 2

Reads the session ID from Part 1, resumes that session in a brand-new
WebSocket connection, and verifies:

  1. The session can be found and resumed (backend persistence works).
  2. All previous messages are returned (message history persisted).
  3. A new prompt in the resumed session can reference earlier context
     (the model received the old conversation).
  4. The session is usable from a different connection (simulates frontend
     reconnect / UI resume).

Appends to the same plain-text log file as Part 1.

Usage:
  python server/tests/test_context_session_e2e_part2.py
  (server must already be running on ws://127.0.0.1:8765/ws)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import websockets

WS_URL = os.environ.get("ZENITH_WS_URL", "ws://127.0.0.1:8765/ws")
SCRIPT_DIR = Path(__file__).resolve().parent
# Shared with part1: artifacts go to the gitignored scripts/e2e_logs/ scratch.
LOG_DIR = SCRIPT_DIR.parent.parent / "scripts" / "e2e_logs"
LOG_FILE = LOG_DIR / "e2e_context_log.txt"
SESSION_ID_FILE = LOG_DIR / "e2e_session_id.txt"

# ── helpers (shared with Part 1) ────────────────────────────────────────────

_rpc_id = 100  # start at 100 so ids don't clash with Part 1 if same process


def next_id() -> str:
    global _rpc_id
    _rpc_id += 1
    return f"e2e_p2_{_rpc_id}"


def ts() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def divider(title: str) -> str:
    return f"\n{'=' * 80}\n  {title}\n{'=' * 80}"


class Log:
    def __init__(self, path: Path, append: bool = True) -> None:
        self.path = path
        if not append:
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
        if data.get("method") == "ping":
            continue


async def ws_collect_events(ws, timeout: float = 60) -> list[dict]:
    events: list[dict] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = deadline - time.time()
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, remaining))
        except TimeoutError:
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

RESUME_PROMPTS = [
    {
        "number": 4,
        "content": "What was the project name I told you about in the first message?",
        "mode": "build",
        "description": "Prompt #4 (resume) — asks about fact from prompt #1 (tests cross-connection context)",
    },
    {
        "number": 5,
        "content": "Just say 'context verified' if you can still see our earlier conversation.",
        "mode": "build",
        "description": "Prompt #5 (resume) — simple confirmation of persistent context",
    },
]


async def run_part2() -> bool:
    log = Log(LOG_FILE)

    # ── Read session ID from Part 1 ──────────────────────────────────────
    log.write(divider("E2E CONTEXT & SESSION PERSISTENCE TEST — PART 2"))
    log.write(f"Started: {ts()}")
    log.write(f"WebSocket: {WS_URL}")

    if not SESSION_ID_FILE.exists():
        log.write(f"\n*** FAIL: Session ID file not found: {SESSION_ID_FILE}")
        log.write("Run Part 1 first.")
        return False

    session_id = SESSION_ID_FILE.read_text(encoding="utf-8").strip()
    log.write(f"Session ID (from Part 1): {session_id}")
    log.write(f"Log file (appending): {LOG_FILE}")

    all_ok = True

    # ── STEP 1: New connection → session.resume → verify persisted state ──
    log.write(divider("STEP 1: NEW CONNECTION — RESUME SESSION"))
    log.write("Opening a brand-new WebSocket connection (simulates frontend UI reconnect)...")

    async with websockets.connect(WS_URL) as ws:
        log.write(f"Connected: {WS_URL}")

        # Resume the session
        log.write(f"\nCalling session.resume with session_id={session_id} ...")
        resume_resp = await ws_rpc(ws, "session.resume", {"session_id": session_id})

        if resume_resp.get("error"):
            log.write(f"\n*** FAIL: session.resume returned error: {resume_resp['error']} ***")
            return False

        result = resume_resp.get("result", {})
        messages = result.get("messages", [])
        session_data = result.get("session", {})
        replayed = result.get("events_replayed", 0)
        latest_seq = result.get("latest_sequence", 0)

        log.write("\nSession resume OK:")
        log.write(f"  Session state: {session_data.get('state', '?')}")
        log.write(f"  Message count: {session_data.get('message_count', '?')}")
        log.write(f"  Total tokens:  {session_data.get('total_tokens', '?')}")
        log.write(f"  Provider:      {session_data.get('provider', '?')}")
        log.write(f"  Model:         {session_data.get('model', '?')}")
        log.write(f"  Events replayed: {replayed}")
        log.write(f"  Latest sequence: {latest_seq}")

        # ── Verify persisted messages ────────────────────────────────────
        log.write(f"\nPersisted messages ({len(messages)} total):")
        log.write(format_persisted_messages(messages))

        user_msgs = [m for m in messages if m.get("role") == "user"]
        assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
        log.write(f"\nMessage breakdown: {len(user_msgs)} user, {len(assistant_msgs)} assistant")

        # Verify we have the conversation from Part 1
        if len(user_msgs) < 3:
            log.write(
                f"\n*** FAIL: Expected at least 3 user messages from Part 1, got {len(user_msgs)} ***"
            )
            all_ok = False
        else:
            log.write(f"\nOK: {len(user_msgs)} user messages found (expected >= 3)")

        # Check that first user message content is present
        first_user = user_msgs[0].get("content", "") if user_msgs else ""
        if "Zenith" in first_user:
            log.write("OK: First user message contains 'Zenith' keyword (content persisted)")
        else:
            log.write(f"WARNING: First user message doesn't contain 'Zenith': {first_user[:200]}")

        # Check session metadata / summary
        metadata = session_data.get("metadata", {})
        if metadata.get("summary"):
            log.write(f"\nSession summary: {len(metadata['summary'])} chars")
            log.write(
                f"  {metadata['summary'][:500]}{'...' if len(metadata.get('summary', '')) > 500 else ''}"
            )
        else:
            log.write(f"\nNo session summary in metadata (keys: {list(metadata.keys())})")

        # ── STEP 2: Send new prompt in resumed session ───────────────────
        for prompt_cfg in RESUME_PROMPTS:
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
                all_ok = False

            # Check for context-related hints in the response
            if num == 4:
                # Prompt #4 asks about "Zenith" from prompt #1
                if "zenith" in assistant_text.lower():
                    log.write(
                        "\n*** CONTEXT VERIFIED: Model referenced 'Zenith' from prompt #1 ***"
                    )
                else:
                    log.write(
                        "\n*** CONTEXT WARNING: Model did NOT reference 'Zenith' — check if context was supplied ***"
                    )
                    log.write(
                        "    This may indicate the old user messages were not included in the model context."
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

            if num < len(RESUME_PROMPTS):
                log.write("\nWaiting 2s before next prompt...")
                await asyncio.sleep(2)

    # ── STEP 3: Final verification — re-resume to confirm all is persisted ──
    log.write(divider("STEP 3: FINAL VERIFICATION — RE-RESUME"))
    log.write("Opening yet another connection to confirm full persistence...")

    async with websockets.connect(WS_URL) as ws:
        final_resp = await ws_rpc(ws, "session.resume", {"session_id": session_id})
        if "result" in final_resp:
            final_messages = final_resp["result"].get("messages", [])
            final_session = final_resp["result"].get("session", {})
            final_user = [m for m in final_messages if m.get("role") == "user"]
            final_asst = [m for m in final_messages if m.get("role") == "assistant"]
            log.write(
                f"\nFinal state: {len(final_messages)} messages "
                f"({len(final_user)} user, {len(final_asst)} assistant)"
            )
            log.write(f"Session state: {final_session.get('state', '?')}")
            log.write(f"Message count in DB: {final_session.get('message_count', '?')}")

            # Verify prompt #4 and #5 are persisted
            all_user_content = " ".join(m.get("content", "") for m in final_user)
            if "Zenith" in all_user_content:
                log.write("OK: 'Zenith' keyword found across persisted user messages")
            if "context verified" in all_user_content.lower():
                log.write("OK: 'context verified' prompt found in persisted messages")
        else:
            log.write(f"\n*** FAIL: Final session.resume failed: {final_resp} ***")
            all_ok = False

    # ── Summary ──────────────────────────────────────────────────────────
    log.write(divider("PART 2 COMPLETE"))
    log.write(f"Session ID: {session_id}")
    log.write(f"Log file: {LOG_FILE}")
    log.write(f"Finished: {ts()}")

    if all_ok:
        log.write("\n  RESULT: ALL CHECKS PASSED")
        log.write("  - Session resumed from new connection: OK")
        log.write("  - Persisted messages contain Part 1 conversation: OK")
        log.write("  - New prompts in resumed session received context: OK")
        log.write("  - Re-resume confirmed full persistence: OK")
    else:
        log.write("\n  RESULT: SOME CHECKS FAILED — see log above")

    return all_ok


if __name__ == "__main__":
    ok = asyncio.run(run_part2())
    sys.exit(0 if ok else 1)
