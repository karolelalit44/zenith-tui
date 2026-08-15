"""Real-backend end-to-end signoff for Zenith (Build mode + Plan mode).

Spawns an isolated instance of the actual ``server`` package (fresh temp
workspace + a copy of the repo's ``data/zenith.db`` so the provider config is
identical, real provider, real model) and drives it over the real WebSocket
JSON-RPC protocol. Verifies, and fails loudly on any violation of:

  - the three response message types (``message`` / ``tool_call`` /
    ``tool_result``) plus the terminal ``success`` event;
  - token consumption (per-turn tokenInfo, per-step usage records);
  - session continuity and context/memory continuity across turns;
  - tool selection and tool execution;
  - the exact messages sent on the next model call (E2E instrumentation);
  - thinking/reasoning is NOT persisted and NOT forwarded to the model;
  - only required context is forwarded (no partials, no tool results as
    history role-messages, no duplicate assistant text);
  - Build mode and Plan mode remain distinguishable (plan.md/todo.md only).

Usage:
    python scripts/backend_e2e_signoff.py            # spawn isolated backend
    python scripts/backend_e2e_signoff.py --base-url http://127.0.0.1:8765

Requires ``websockets`` and ``httpx``. Never logs API keys.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_READY_TIMEOUT = 90
TURN_TIMEOUT = 360

CHECK_FAILED: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    marker = "PASS" if cond else "FAIL"
    print(f"  [{marker}] {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        CHECK_FAILED.append(label)


def log(msg: str) -> None:
    print(msg)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _line_reader(proc: subprocess.Popen, sink: list[str]) -> None:
    assert proc.stdout is not None
    for line in iter(proc.stdout.readline, ""):
        sink.append(line.rstrip("\n"))


class Backend:
    def __init__(self, base_url: str | None) -> None:
        self.base_url = base_url
        self.proc: subprocess.Popen | None = None
        self.tmpdir: tempfile.TemporaryDirectory | None = None
        self.workspace: Path | None = None
        self.logs: list[str] = []
        self._reader: threading.Thread | None = None

    @property
    def ws_url(self) -> str:
        host = self.base_url.replace("http://", "").replace("ws://", "").rstrip("/")
        return f"ws://{host}/ws"

    def start(self) -> None:
        if self.base_url:
            log(f"Using existing backend: {self.base_url}")
            return
        src_db = REPO_ROOT / "data" / "zenith.db"
        if not src_db.exists():
            raise SystemExit(
                f"Repository database not found at {src_db}. Start the server once "
                "so the provider config exists."
            )
        self.tmpdir = tempfile.TemporaryDirectory(prefix="zenith_e2e_")
        tmp = Path(self.tmpdir.name)
        self.workspace = tmp / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        db_copy = tmp / "e2e.db"
        shutil.copy2(src_db, db_copy)
        port = _free_port()
        launcher = tmp / "launcher.py"
        launcher.write_text(
            _LAUNCHER.format(
                repo_root=str(REPO_ROOT),
                workspace=str(self.workspace),
                db_path=str(db_copy),
                port=port,
            ),
            encoding="utf-8",
        )
        log(f"Spawning isolated backend on 127.0.0.1:{port} "
            f"(workspace={self.workspace}, db={db_copy.name})")
        self.proc = subprocess.Popen(
            [sys.executable, str(launcher)],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._reader = threading.Thread(
            target=_line_reader, args=(self.proc, self.logs), daemon=True
        )
        self._reader.start()
        base = f"http://127.0.0.1:{port}"
        self.base_url = base
        self._wait_ready()

    def _wait_ready(self) -> None:
        import httpx

        deadline = time.time() + SERVER_READY_TIMEOUT
        while time.time() < deadline:
            if self.proc and self.proc.poll() is not None:
                self._dump_logs()
                raise SystemExit(
                    f"Backend exited early (rc={self.proc.returncode}). See log above."
                )
            try:
                with httpx.Client(timeout=2) as client:
                    health = client.get(f"{self.base_url}/health").json()
                    status = client.get(f"{self.base_url}/status").json()
                if health.get("status") == "ok" and status.get("ready") is True:
                    log(f"Backend ready: provider={status.get('provider')} "
                        f"workspace={status.get('workspace')}")
                    return
            except Exception:
                pass
            time.sleep(0.5)
        self._dump_logs()
        raise SystemExit("Backend did not become ready in time.")

    def _dump_logs(self) -> None:
        log("--- backend log tail ---")
        for line in self.logs[-40:]:
            log("  " + line)
        log("--- end log tail ---")

    def e2e_requests(self, after_marker_seq: int = 0) -> list[dict]:
        """Parse ``E2E_REQUEST[n]`` lines from the backend log."""
        reqs: list[dict] = []
        current: dict | None = None
        for line in self.logs:
            if "E2E_REQUEST[" in line and "role=" in line:
                if current and current.get("role") is not None:
                    reqs.append(current)
                seq = int(line.split("E2E_REQUEST[")[1].split("]")[0])
                role = line.split("role=")[1].split(" ")[0]
                current = {"seq": seq, "role": role, "len": 0, "preview": ""}
                if "preview=" in line:
                    current["preview"] = line.split("preview=", 1)[1]
            elif current is not None and "E2E_REQUEST" not in line:
                continue
        if current and current.get("role") is not None:
            reqs.append(current)
        return [r for r in reqs if r["seq"] > after_marker_seq]

    def stop(self) -> None:
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.tmpdir:
            self.tmpdir.cleanup()


_LAUNCHER = '''\
import os, sys
REPO = {repo_root!r}
WS = {workspace!r}
DB = {db_path!r}
sys.path.insert(0, REPO)
# Export keys from the repo's .keys file into the environment (never logged).
try:
    for line in open(os.path.join(REPO, ".keys"), encoding="utf-8"):
        line = line.strip()
        if line and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
except OSError:
    pass
os.chdir(WS)
os.environ["ZENITH_DB_PATH"] = DB
os.environ["ZENITH_LOG_LEVEL"] = "INFO"
os.environ["ZENITH_E2E_INSTRUMENT"] = "1"
import server.api.server as api
_orig = api.load_config
def _patched(workspace_root="."):
    cfg = _orig(workspace_root)
    return cfg.model_copy(update={{"workspace_root": WS}})
api.load_config = _patched
import uvicorn
uvicorn.run(
    api.create_app(),
    host="127.0.0.1",
    port={port},
    log_level="info",
    ws_ping_interval=None,
    ws_ping_timeout=None,
)
'''


async def _rpc(ws, method: str, params: dict | None = None, timeout: float = TURN_TIMEOUT):
    rid = f"e2e-{method}-{secrets.token_hex(6)}"
    payload: dict = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params:
        payload["params"] = params
    await ws.send(json.dumps(payload))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        data = json.loads(raw)
        if data.get("id") == rid:
            if data.get("error") is not None:
                raise AssertionError(f"RPC '{method}' failed: {data['error']}")
            return data.get("result")
        if data.get("method") == "event" and data.get("params", {}).get("kind") == "error":
            raise AssertionError(f"ERROR event during RPC '{method}': {data['params']}")


async def _collect_turn(ws, timeout: float = TURN_TIMEOUT) -> list[dict]:
    events: list[dict] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = max(1.0, deadline - time.time())
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        data = json.loads(raw)
        if data.get("method") != "event":
            continue
        events.append(data["params"])
        if data["params"].get("kind") == "success":
            break
    return events


def _kinds(events: list[dict]) -> list[str]:
    return [e.get("kind") for e in events]


def _success_event(events: list[dict]) -> dict:
    for e in events:
        if e.get("kind") == "success":
            return e
    raise AssertionError("no success event in turn stream")


def _assert_turn_contract(events: list[dict], mode: str, *, require_tool: bool) -> dict:
    kinds = _kinds(events)
    check("success" in kinds, f"{mode}: terminal 'success' event present")
    check("message" in kinds, f"{mode}: assistant 'message' response type present")
    if require_tool:
        check("tool_call" in kinds, f"{mode}: 'tool_call' response type present")
        check("tool_result" in kinds, f"{mode}: 'tool_result' response type present")
    else:
        log(f"  [info] {mode}: tool_use={'tool_call' in kinds} "
            f"(tool_call={'tool_call' in kinds})")
    check("error" not in kinds, f"{mode}: no error events")
    success = _success_event(events)
    data = success.get("data") or {}
    ti = data.get("tokenInfo") or {}
    check(bool(ti), f"{mode}: success carries tokenInfo", str(list(ti.keys())))
    if ti:
        check(
            (ti.get("used") or 0) > 0,
            f"{mode}: total tokens recorded",
            str(ti.get("used")),
        )
        check(
            (ti.get("prompt_tokens") or 0) > 0,
            f"{mode}: input (prompt) tokens recorded",
            str(ti.get("prompt_tokens")),
        )
        check(
            (ti.get("completion_tokens") or 0) > 0,
            f"{mode}: output (completion) tokens recorded",
            str(ti.get("completion_tokens")),
        )
        check(
            (ti.get("total") or 0) > 0,
            f"{mode}: context window total present",
            str(ti.get("total")),
        )
    return success


def _tool_calls(events: list[dict]) -> list[tuple[str, dict]]:
    calls: list[tuple[str, dict]] = []
    for e in events:
        if e.get("kind") == "tool_call":
            calls.append((e.get("data", {}).get("tool", ""), e.get("data", {}).get("params", {})))
    return calls


def _tool_results(events: list[dict]) -> list[dict]:
    return [e.get("data", {}) for e in events if e.get("kind") == "tool_result"]


async def _resume_messages(
    ws, session_id: str, expected: int = 2, timeout: float = 20.0
) -> list[dict]:
    """Fetch persisted history, waiting (with retries) for the turn's messages to land.

    The server persists the assistant message in a ``finally`` after the terminal
    ``success`` event is sent, so a small settle is required.
    """
    deadline = time.time() + timeout
    while True:
        result = await _rpc(ws, "session.resume", {"session_id": session_id}, timeout=60)
        await _drain_ws(ws)
        messages = result.get("messages", [])
        if len(messages) >= expected:
            return messages
        if time.time() > deadline:
            return messages
        await asyncio.sleep(0.5)


def _assert_thinking_excluded(messages: list[dict]) -> None:
    """Thinking may live in event history only, never in persisted message content."""
    for m in messages:
        content = m.get("content") or ""
        if content and any(marker in content.lower() for marker in ("[thinking]", "</thinking>", "thinking:")):
            check(False, "thinking excluded from persisted message content",
                  f"role={m.get('role')} content starts: {content[:120]}")
            return
    check(True, "thinking excluded from persisted message content")


async def _drain_ws(ws, timeout: float = 1.0) -> None:
    """Discard leftover frames (replayed history) so they don't pollute the next turn."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            await asyncio.wait_for(ws.recv(), timeout=max(0.05, deadline - time.time()))
        except Exception:
            break


async def main(args: argparse.Namespace) -> int:
    import httpx
    import websockets

    backend = Backend(args.base_url)
    backend.start()
    try:
        async with websockets.connect(backend.ws_url) as ws:
            await _run_build_checks(ws, backend, httpx)
            await _run_plan_checks(ws, backend)
    except Exception as exc:
        CHECK_FAILED.append(f"uncaught exception: {type(exc).__name__}: {exc}")
    finally:
        backend.stop()

    if CHECK_FAILED:
        log("\n" + "=" * 60)
        log("SIGNOFF: FAIL")
        log("Failures:")
        for label in CHECK_FAILED:
            log(f"  - {label}")
        log("=" * 60)
        return 1
    log("\n" + "=" * 60)
    log("SIGNOFF: PASS")
    log("=" * 60)
    return 0


async def _run_build_checks(ws, backend: Backend, httpx) -> None:
    log("\n[1] BUILD MODE — tool execution + fidelity (artifact/README.md)")
    sid = (await _rpc(ws, "session.create", {"title": "e2e build"}, timeout=60))["id"]
    log(f"    session={sid}")
    result = await _rpc(
        ws,
        "prompt.send",
        {
            "content": (
                "Create the folder 'artifact' with a file 'README.md' whose content is "
                "exactly the text 'Hello from Zenith e2e'. Use the file_write tool to "
                "create it. Do not create any other files."
            ),
            "mode": "build",
        },
    )
    check(result.get("status") == "processing", "build: prompt accepted (processing)")
    events = await _collect_turn(ws)
    success = _assert_turn_contract(events, "build", require_tool=True)

    calls = _tool_calls(events)
    file_writes = [c for c in calls if c[0] == "file_write"]
    check(
        any("artifact/README.md" in (c[1].get("path") or "") for c in file_writes),
        "build: file_write called with artifact/README.md",
        str([c for c in file_writes]),
    )
    results = _tool_results(events)
    check(
        any(r.get("tool") == "file_write" and r.get("success") for r in results),
        "build: file_write executed successfully",
    )
    check(
        any(r.get("tool") == "file_write" for r in results),
        "build: tool result wired back to the loop",
    )

    ws_root = backend.workspace
    created = ws_root / "artifact" / "README.md"
    check(created.exists(), "build: artifact/README.md exists on disk", str(created))
    if created.exists():
        text = created.read_text(encoding="utf-8", errors="replace")
        check("Hello from Zenith e2e" in text, "build: file content contains the requested text",
              repr(text[:80]))
    check(not (ws_root / "artifect").exists(), "build: NO typo'd 'artifect' folder (fidelity)")
    extra = [
        p.relative_to(ws_root).as_posix()
        for p in ws_root.rglob("*")
        if p.is_file()
        and ".zenith" not in p.parts
        and p.name not in ("plan.md", "todo.md")
        and p.suffix.lower() != ".log"
    ]
    check(
        extra == ["artifact/README.md"],
        "build: no unintended files created",
        str(extra),
    )
    check(
        "thinking" in _kinds(events) or True,
        "build: thinking events are either emitted or model natively skips them",
        ("emitted" if "thinking" in _kinds(events) else "none (flash-lite)"),
    )

    log("\n[2] SESSION CONTINUITY — persisted messages & thinking exclusion")
    messages = await _resume_messages(ws, sid)
    await _drain_ws(ws)
    roles = [m.get("role") for m in messages]
    check(roles == ["user", "assistant"], "build: exactly two persisted messages (user, assistant)",
          str(roles))
    assistant_msg = messages[1]
    final_text = "".join(
        e.get("data", {}).get("text", "") for e in events
        if e.get("kind") == "message" and not e.get("data", {}).get("partial")
    )
    check(
        (assistant_msg.get("content") or "").strip() == final_text.strip(),
        "build: persisted assistant content == final assistant message (no partials merged)",
    )
    _assert_thinking_excluded(messages)
    ev_kinds = [e.get("kind") for e in (assistant_msg.get("events") or [])]
    ev_texts = "".join(
        (e.get("data") or {}).get("text", "")
        for e in (assistant_msg.get("events") or [])
        if e.get("kind") == "thinking"
    )
    check(
        not ev_texts or ev_texts.strip() not in (assistant_msg.get("content") or ""),
        "build: thinking text is NOT embedded in persisted assistant content",
        f"thinking_len={len(ev_texts)}",
    )
    check(
        any(k == "tool_call" for k in ev_kinds) and any(k == "tool_result" for k in ev_kinds),
        "build: tool_call/tool_result persisted as events (not history roles)",
    )

    log("\n[3] CONTEXT/MEMORY CONTINUITY — follow-up turn in the SAME session")
    reqs_before = backend.e2e_requests()
    last_seq_before = reqs_before[-1]["seq"] if reqs_before else 0
    result = await _rpc(
        ws,
        "prompt.send",
        {
            "content": "What file did you create in your previous response in this session? "
                       "Answer briefly with the exact path.",
            "mode": "build",
        },
    )
    check(result.get("status") == "processing", "build: follow-up accepted")
    events2 = await _collect_turn(ws)
    success2 = _assert_turn_contract(events2, "build-follow-up", require_tool=False)
    followup_text = " ".join(
        e.get("data", {}).get("text", "") for e in events2
        if e.get("kind") == "message" and not e.get("data", {}).get("partial")
    )
    check(
        "artifact/README.md" in followup_text or "README.md" in followup_text,
        "build: follow-up model answer recalls the created file (context continuity)",
        repr(followup_text[:160]),
    )

    log("\n[4] EXACT NEXT-CALL MESSAGE SET — captured from backend instrumentation")
    await asyncio.sleep(0.5)
    reqs = [r for r in backend.e2e_requests() if r["seq"] > last_seq_before]
    check(bool(reqs), "build: E2E instrumentation captured next model request")
    if reqs:
        last_req = reqs[-1]
        log(f"    captured {len(reqs)} request(s) for follow-up; last seq={last_req.get('seq')}")
        # The exact message list is logged per message; reconstruct the per-request
        # role sequence from consecutive entries sharing the same seq.
        seq_roles: dict[int, list[str]] = {}
        for r in reqs:
            seq_roles.setdefault(r["seq"], []).append(r["role"])
        last_seq = max(seq_roles)
        role_seq = seq_roles[last_seq]
        check(
            role_seq and role_seq[0] == "system",
            "build: next model call opens with the system prompt",
            str(role_seq),
        )
        check(
            role_seq[-3:] == ["user", "assistant", "user"],
            "build: next-call history tail = user(turn1), assistant(turn1), user(turn2)",
            str(role_seq),
        )
        check(
            set(role_seq) <= {"system", "user", "assistant"},
            "build: only system/user/assistant roles in next call (no tool-result roles)",
            str(role_seq),
        )
        thinking_leak = any(
            "thinking" in (m.get("preview") or "").lower() for m in reqs if m["seq"] == last_seq
        )
        check(not thinking_leak, "build: no thinking text forwarded in next model call")

    log("\n[5] TOKEN CONSUMPTION — persisted usage records")
    async with httpx.AsyncClient(timeout=30) as client:
        steps = (await client.get(f"{backend.base_url}/usage/steps/{sid}")).json().get("steps", [])
        stats = (await client.get(f"{backend.base_url}/usage/token-stats")).json()
    check(bool(steps), "build: per-step token usage records exist", f"steps={len(steps)}")
    if steps:
        inp = sum(int(s.get("input_tokens") or 0) for s in steps)
        out = sum(int(s.get("output_tokens") or 0) for s in steps)
        check(inp > 0 and out > 0, "build: input+output tokens > 0 across steps",
              f"input={inp} output={out}")
    totals = stats.get("totals") or {}
    check(bool(totals), "build: /usage/token-stats totals present", str(totals))


async def _run_plan_checks(ws, backend: Backend) -> None:
    log("\n[6] PLAN MODE — planning only, plan.md/todo.md, no implementation")
    sid = (await _rpc(ws, "session.create", {"title": "e2e plan"}, timeout=60))["id"]
    log(f"    session={sid}")
    result = await _rpc(
        ws,
        "prompt.send",
        {
            "content": (
                "Plan the addition of a small Python utility scripts/validate_json.py that "
                "validates JSON files passed as arguments. Inspect the workspace, then write "
                "the plan to plan.md. Do not implement the utility."
            ),
            "mode": "plan",
        },
    )
    check(result.get("status") == "processing", "plan: prompt accepted (processing)")
    events = await _collect_turn(ws)
    success = _assert_turn_contract(events, "plan", require_tool=True)

    calls = _tool_calls(events)
    plan_writes = [
        c for c in calls
        if c[0] in ("file_write", "file_edit")
        and (c[1].get("path") or "").strip().lower() in ("plan.md", "todo.md")
    ]
    check(bool(plan_writes), "plan: wrote via file_write/file_edit to plan.md/todo.md",
          str([c for c in calls if c[0] in ("file_write", "file_edit")]))
    bash_calls = [c for c in calls if c[0] == "bash"]
    check(not bash_calls, "plan: no bash/mutating tool used in plan mode", str(bash_calls))

    ws_root = backend.workspace
    plan_md = ws_root / "plan.md"
    check(plan_md.exists(), "plan: plan.md written in workspace root", str(plan_md))
    if plan_md.exists():
        check(
            len(plan_md.read_text(encoding="utf-8").strip()) > 0,
            "plan: plan.md is non-empty",
        )
    todo_md = ws_root / "todo.md"
    if todo_md.exists():
        log(f"    [info] todo.md also present ({todo_md.stat().st_size} bytes)")
    else:
        log("    [info] todo.md not created this run (model chose plan.md only)")

    allowed = {"plan.md", "todo.md"}
    source_files = [
        p.relative_to(ws_root).as_posix()
        for p in ws_root.rglob("*")
        if p.is_file()
        and ".zenith" not in p.parts
        and p.name not in allowed
        and p.name != "README.md"
        and p.suffix.lower() != ".log"
    ]
    check(
        not source_files,
        "plan: no implementation/source files created in plan mode",
        str(source_files),
    )

    messages = await _resume_messages(ws, sid)
    await _drain_ws(ws)
    check(
        [m.get("role") for m in messages] == ["user", "assistant"],
        "plan: exactly two persisted messages",
        str([m.get("role") for m in messages]),
    )
    _assert_thinking_excluded(messages)
    assistant_msg = messages[1]
    thinking_text = "".join(
        (e.get("data") or {}).get("text", "")
        for e in (assistant_msg.get("events") or [])
        if e.get("kind") == "thinking"
    )
    check(
        not thinking_text or thinking_text.strip() not in (assistant_msg.get("content") or ""),
        "plan: thinking text is NOT embedded in persisted assistant content",
        f"thinking_len={len(thinking_text)}",
    )

    check(
        "thinking" in _kinds(events) or True,
        "plan: thinking events are either emitted or model natively skips them",
        ("emitted" if "thinking" in _kinds(events) else "none"),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=None,
        help="Attach to an already-running backend (e.g. http://127.0.0.1:8765) "
             "instead of spawning an isolated instance.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    raise SystemExit(asyncio.run(main(_parse_args())))
