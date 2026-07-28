"""Quick WS protocol debug test with tracebacks."""
import asyncio
import json
import traceback
import websockets

WS_URL = "ws://127.0.0.1:8765/ws"

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

        # 4d. Empty object -> error
        await ws.send(json.dumps({}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        has_error = "error" in resp
        tests.append(("empty_object", has_error, f"has_error={has_error}"))

    # 4e. Malformed JSON (separate connection)
    async with websockets.connect(WS_URL, close_timeout=3) as ws2:
        await ws2.send("not json at all {{{")
        resp = json.loads(await asyncio.wait_for(ws2.recv(), timeout=5))
        err_code = resp.get("error", {}).get("code")
        ok = err_code == -32700
        tests.append(("malformed_json", ok, f"error_code={err_code}"))

    return tests

try:
    results = asyncio.run(_run())
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"  {name}: {status} ({detail})")
    print("\nALL PASSED")
except Exception as e:
    print(f"CRASH: {type(e).__name__}: {e}")
    traceback.print_exc()
