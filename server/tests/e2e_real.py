from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import websockets

BACKEND_PORT = 18765
BACKEND_URL = f"http://localhost:{BACKEND_PORT}"
WS_URL = f"ws://localhost:{BACKEND_PORT}/ws"
ZENITH_DIR = Path(__file__).resolve().parent.parent


def log(msg: str) -> None:
    print(f"[E2E] {msg}", flush=True)


async def wait_for_backend(timeout: int = 30) -> bool:
    import httpx

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{BACKEND_URL}/health", timeout=2)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("handler"):
                        log(f"Backend ready (PID {data.get('version', '?')})")
                        return True
        except Exception:
            pass
        await asyncio.sleep(0.5)
    log("Backend did not become ready")
    return False


async def test_health_rest() -> dict:
    import httpx

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BACKEND_URL}/health", timeout=5)
        assert r.status_code == 200, f"health failed: {r.status_code}"
        data = r.json()
        assert data.get("status") == "ok", f"unexpected health: {data}"
        log(f"REST /health: {data}")
        return data


async def test_startup_validate() -> dict:
    import httpx

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BACKEND_URL}/startup/validate", timeout=5)
        assert r.status_code == 200, f"startup/validate failed: {r.status_code}"
        data = r.json()
        log(
            f"REST /startup/validate: status={data.get('status')}, provider={data.get('active_provider')}, missing={data.get('missing')}"
        )
        return data


async def test_websocket_health() -> None:
    async with websockets.connect(WS_URL) as ws:
        req = json.dumps({"jsonrpc": "2.0", "id": "1", "method": "health"})
        await ws.send(req)
        resp = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(resp)
        assert data.get("result") == {"status": "ok"}, f"WS health failed: {data}"
        log(f"WS health: {data['result']}")


async def test_session_lifecycle() -> str:
    async with websockets.connect(WS_URL) as ws:
        req = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "2",
                "method": "session.create",
                "params": {"title": "E2E Test"},
            }
        )
        await ws.send(req)
        resp = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(resp)
        assert "result" in data, f"session.create failed: {data}"
        session_id = data["result"]["id"]
        log(f"Session created: {session_id}")
        req = json.dumps({"jsonrpc": "2.0", "id": "3", "method": "session.list"})
        await ws.send(req)
        resp = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(resp)
        sessions = data.get("result", [])
        assert any(s["id"] == session_id for s in sessions), f"session not in list: {sessions}"
        log(f"Session list OK ({len(sessions)} sessions)")
        return session_id


async def test_prompt_submission(session_id: str, model_override: str | None = None) -> list[dict]:
    async with websockets.connect(WS_URL) as ws:
        params: dict = {
            "content": "Write a one-line Python function that returns the sum of two numbers.",
            "mode": "build",
            "session_id": session_id,
        }
        if model_override:
            params["model"] = model_override
        req = json.dumps({"jsonrpc": "2.0", "id": "4", "method": "prompt.send", "params": params})
        await ws.send(req)
        events: list[dict] = []
        while True:
            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=30)
            except TimeoutError:
                log("Timed out waiting for events")
                break
            data = json.loads(resp)
            if "method" in data and data["method"] == "event":
                events.append(data["params"])
                kind = data["params"].get("kind", "")
                if kind in ("success", "error"):
                    log(f"Terminal event: {kind}")
                    break
            elif "result" in data:
                log(f"Response: {data['result']}")
            elif "error" in data:
                log(f"Error: {data['error']}")
                events.append({"kind": "error", "data": data["error"]})
                break
        log(f"Collected {len(events)} events, kinds: {[e.get('kind') for e in events]}")
        return events


async def test_workspace_status() -> None:
    async with websockets.connect(WS_URL) as ws:
        req = json.dumps({"jsonrpc": "2.0", "id": "5", "method": "workspace.status"})
        await ws.send(req)
        resp = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(resp)
        assert "result" in data, f"workspace.status failed: {data}"
        log(f"Workspace status: git={data['result'].get('git', {}).get('branch', 'N/A')}")


async def run_all_tests() -> bool:
    tests = [
        ("REST /health", test_health_rest),
        ("REST /startup/validate", test_startup_validate),
        ("WS health", test_websocket_health),
        ("Session lifecycle", lambda: test_session_lifecycle()),
    ]
    results = []
    for name, coro_fn in tests:
        try:
            if name == "Session lifecycle":
                session_id = await coro_fn()
                results.append((name, True, session_id))
            else:
                await coro_fn()
                results.append((name, True, None))
            log(f"  ✓ {name}")
        except Exception as e:
            results.append((name, False, str(e)))
            log(f"  ✗ {name}: {e}")
    session_id = None
    for name, ok, val in results:
        if name == "Session lifecycle" and ok:
            session_id = val
    if session_id:
        reliable_models = [
            "google/gemini-2.0-flash-exp:free",
            "openrouter/auto",
            "meta-llama/llama-3.1-8b-instruct",
        ]
        prompt_ok = False
        events = []
        for model in reliable_models:
            try:
                log(f"Trying prompt with model: {model}")
                events = await test_prompt_submission(session_id, model_override=model)
                kinds = [e.get("kind") for e in events]
                if "success" in kinds:
                    prompt_ok = True
                    log(f"  ✓ Prompt with {model} succeeded")
                    break
                elif "error" in kinds:
                    err_msg = next(
                        (
                            e.get("data", {}).get("message", "")
                            for e in events
                            if e.get("kind") == "error"
                        ),
                        "",
                    )
                    log(f"  Model {model} returned error: {err_msg}")
            except Exception as e:
                log(f"  Model {model} failed: {e}")
        results.append(("Prompt submission", prompt_ok, events))
        if prompt_ok:
            log("  ✓ Prompt submission succeeded")
        else:
            log("  ✗ All prompt models failed")
    else:
        results.append(("Prompt submission (skipped)", True, "no session"))
    try:
        await test_workspace_status()
        results.append(("Workspace status", True, None))
        log("  ✓ Workspace status")
    except Exception as e:
        results.append(("Workspace status", False, str(e)))
        log(f"  ✗ Workspace status: {e}")
    print()
    print("=" * 60)
    print("  E2E TEST RESULTS")
    print("=" * 60)
    all_ok = True
    for name, ok, _ in results:
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"  {status}  {name}")
        if not ok:
            all_ok = False
    print("=" * 60)
    print(f"  Overall: {('ALL PASS' if all_ok else 'SOME FAILED')}")
    print("=" * 60)
    return all_ok


async def main():
    os.chdir(str(ZENITH_DIR.parent))
    log("Starting zenith server...")
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "uvicorn",
        "server.api.server:create_app",
        "--factory",
        "--host",
        "localhost",
        "--port",
        str(BACKEND_PORT),
        "--log-level",
        "info",
        cwd=str(ZENITH_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async def reader():
        assert proc.stdout
        async for line in proc.stdout:
            text = line.decode("utf-8", errors="replace").rstrip()
            if any(kw in text for kw in ("ERROR", "WARNING", "ready", "accepted")):
                print(f"  [BACKEND] {text}", flush=True)

    asyncio.create_task(reader())
    try:
        ready = await wait_for_backend(timeout=20)
        if not ready:
            log("Backend failed to start")
            proc.terminate()
            sys.exit(1)
        ok = await run_all_tests()
        if not ok:
            log("Some tests failed!")
            sys.exit(1)
        log("All E2E tests passed!")
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except TimeoutError:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(main())
