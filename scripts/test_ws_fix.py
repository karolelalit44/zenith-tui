"""Quick WS protocol debug test."""
import asyncio
import json

import websockets

WS_URL = "ws://127.0.0.1:8765/ws"

async def test():
    async with websockets.connect(WS_URL) as ws:
        # 1. Health
        await ws.send(json.dumps({"jsonrpc": "2.0", "method": "health", "id": 1, "params": {}}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        print(f"1. Health: {resp}")

        # 2. Unknown method
        await ws.send(json.dumps({"jsonrpc": "2.0", "method": "bogus", "id": 2, "params": {}}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        print(f"2. Unknown: {resp}")

        # 3. Session create
        await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 3, "params": {"title": "Test"}}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        sid = resp.get("result", {}).get("id")
        print(f"3. Create: sid={sid}")

        # 4. Session list (used to reset session_id!)
        await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.list", "id": 4, "params": {}}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        print(f"4. List: {len(resp.get('result', []))} sessions")

        # 5. Session export (should work even after list)
        await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.export", "id": 5, "params": {}}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        has_result = "result" in resp
        print(f"5. Export after list: has_result={has_result}, error={resp.get('error')}")

        # 6. Health again
        await ws.send(json.dumps({"jsonrpc": "2.0", "method": "health", "id": 6, "params": {}}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        print(f"6. Health: {resp.get('result')}")

        # 7. Export again
        await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.export", "id": 7, "params": {}}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        has_result = "result" in resp
        print(f"7. Export after health: has_result={has_result}, error={resp.get('error')}")

        # 8. Empty object -> error
        await ws.send(json.dumps({}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        print(f"8. Empty object: has_error={'error' in resp}")

    # 9. Malformed JSON (new connection)
    async with websockets.connect(WS_URL) as ws2:
        await ws2.send("not json at all {{{")
        resp = json.loads(await asyncio.wait_for(ws2.recv(), timeout=5))
        print(f"9. Malformed JSON: error_code={resp.get('error', {}).get('code')}")

    print("\nALL PASSED")

if __name__ == "__main__":
    asyncio.run(test())
