import asyncio
import json
import time

import websockets

WS_URL = "ws://127.0.0.1:8765/ws"

async def single_client():
    print("=== Single client test ===")
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 1, "params": {"title": "Debug"}}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        sid = resp.get("result", {}).get("id")
        print(f"Session: {sid}")

        await ws.send(json.dumps({"jsonrpc": "2.0", "method": "prompt.send", "id": 2, "params": {"content": "What is 2+2? Just the number.", "session_id": sid, "mode": "default"}}))

        t0 = time.time()
        while time.time() - t0 < 30:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
                elapsed = round((time.time() - t0) * 1000)
                kind = msg.get("params", {}).get("kind") if msg.get("params") else None
                is_result = "result" in msg
                print(f"  [{elapsed}ms] kind={kind} is_result={is_result}")
                if kind in ("success", "error"):
                    print("Terminal!")
                    break
            except TimeoutError:
                print(f"  timeout at {round((time.time()-t0)*1000)}ms")
                break


async def stress_5():
    print("\n=== 5-client stress test ===")

    async def client(idx):
        time.time()
        try:
            async with websockets.connect(WS_URL) as ws:
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": idx * 10 + 1, "params": {"title": f"Stress {idx}"}}))
                resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                sid = resp.get("result", {}).get("id")
                print(f"  Client {idx}: session={sid}")

                t_prompt = time.time()
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "prompt.send", "id": idx * 10 + 2, "params": {"content": f"What is {idx}+{idx}? Just the number.", "session_id": sid, "mode": "default"}}))

                events = []
                while time.time() - t_prompt < 20:
                    try:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
                        kind = msg.get("params", {}).get("kind") if msg.get("params") else None
                        is_result = "result" in msg
                        if kind:
                            events.append(kind)
                            print(f"  Client {idx}: [{round((time.time()-t_prompt)*1000)}ms] event={kind}")
                        elif is_result:
                            print(f"  Client {idx}: [{round((time.time()-t_prompt)*1000)}ms] result")
                        if kind in ("success", "error"):
                            break
                    except TimeoutError:
                        print(f"  Client {idx}: timeout at {round((time.time()-t_prompt)*1000)}ms")
                        continue
                print(f"  Client {idx}: DONE events={events}")
                return events
        except Exception as e:
            print(f"  Client {idx}: ERROR {e}")
            return []

    results = await asyncio.gather(*[client(i) for i in range(5)])
    for i, events in enumerate(results):
        terminal = "yes" if "success" in events or "error" in events else "NO"
        print(f"  Client {i}: terminal={terminal} count={len(events)}")


if __name__ == "__main__":
    asyncio.run(single_client())
    asyncio.run(stress_5())
