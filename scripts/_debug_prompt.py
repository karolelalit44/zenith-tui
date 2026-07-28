"""Debug LLM prompt.send error."""
import asyncio
import json
import time
import sys
import os
sys.path.insert(0, r"D:\vdo\code\zenith-frontend-tui")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

for line in open(r"D:\vdo\code\zenith-frontend-tui\.keys").readlines():
    if "=" in line:
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

from subprocess import Popen, DEVNULL, PIPE
from pathlib import Path
ROOT = Path(__file__).parent.parent

proc = Popen(
    [str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "main.py"), "serve"],
    cwd=str(ROOT), stdout=DEVNULL, stderr=PIPE, encoding="utf-8", errors="replace",
)
time.sleep(7)

if proc.poll() is not None:
    print("Server failed to start")
    sys.exit(1)

import websockets

async def test():
    async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:
        await ws.send(json.dumps({"jsonrpc": "2.0", "method": "session.create", "id": 1, "params": {"title": "Debug"}}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
        sid = resp["result"]["id"]
        print(f"Session: {sid}")

        await ws.send(json.dumps({
            "jsonrpc": "2.0", "method": "prompt.send", "id": 2,
            "params": {"content": "Say exactly: hello", "session_id": sid, "mode": "build"}
        }))
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), 10)
                msg = json.loads(raw)
                kind = msg.get("params", {}).get("kind")
                data = msg.get("params", {}).get("data", {})
                if kind:
                    print(f"EVENT: {kind} -- {json.dumps(data)[:300]}")
                elif "error" in msg:
                    print(f"JSONRPC ERROR: {json.dumps(msg['error'])[:500]}")
                elif "result" in msg:
                    print(f"RESULT: {json.dumps(msg['result'])[:300]}")
                if kind in ("success", "error"):
                    break
            except asyncio.TimeoutError:
                print(f"recv timeout ({int(time.time() - deadline + 90)}s elapsed)")
                continue

asyncio.run(test())

# Also print server stderr
proc.terminate()
try:
    out, err = proc.communicate(timeout=5)
    if err:
        lines = err.strip().splitlines()
        for line in lines[-20:]:
            print(f"SERVER: {line}")
except Exception:
    proc.kill()
