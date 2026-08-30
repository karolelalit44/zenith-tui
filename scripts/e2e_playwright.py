"""
Playwright E2E test: Opens a browser, connects to the backend WebSocket directly,
sends prompts, waits for completion, and analyzes every aspect of the response.

Usage:
    python scripts/e2e_playwright.py
    python scripts/e2e_playwright.py --timeout 120
    python scripts/e2e_playwright.py --headless false   # show browser
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
LOG_DIR = REPO_ROOT / "scripts" / "e2e_logs"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8765
WS_URL = f"ws://{BACKEND_HOST}:{BACKEND_PORT}/ws"
HEALTH_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/health"

JS_SETUP = """
({ wsUrl }) => {
    return new Promise((resolve, reject) => {
        const ws = new WebSocket(wsUrl);
        let id = 1;
        const pending = new Map();
        const events = [];
        let connected = false;

        ws.onopen = () => { connected = true; };

        ws.onmessage = (evt) => {
            try {
                const msg = JSON.parse(evt.data);
                if (msg.id && pending.has(msg.id)) {
                    pending.get(msg.id)(msg);
                    pending.delete(msg.id);
                }
                if (msg.method === 'event') {
                    events.push({ kind: msg.params.kind, data: msg.params.data, ts: Date.now() });
                }
            } catch {}
        };

        ws.onerror = (e) => { if (!connected) reject(new Error('WS connection failed')); };

        function rpc(method, params, timeout) {
            return new Promise((res, rej) => {
                const rid = String(id++);
                const timer = setTimeout(() => { pending.delete(rid); rej(new Error('Timeout: ' + method)); }, (timeout || 15) * 1000);
                pending.set(rid, (msg) => { clearTimeout(timer); res(msg); });
                ws.send(JSON.stringify({ jsonrpc: '2.0', id: rid, method, params }));
            });
        }

        function stream(method, params, waitKind, timeout) {
            return new Promise((res, rej) => {
                const before = events.length;
                const rid = String(id++);
                const timer = setTimeout(() => {
                    pending.delete(rid);
                    const evts = events.slice(before);
                    rej(new Error('Timeout waiting for ' + waitKind + ', got: ' + evts.map(e => e.kind).join(',')));
                }, (timeout || 90) * 1000);
                pending.set(rid, () => {});
                ws.send(JSON.stringify({ jsonrpc: '2.0', id: rid, method, params }));
                const poll = setInterval(() => {
                    const evts = events.slice(before);
                    const terminal = evts.find(e => e.kind === waitKind);
                    const errorEv = evts.find(e => e.kind === 'error');
                    if (terminal) {
                        clearTimeout(timer); clearInterval(poll); pending.delete(rid);
                        res({ ok: true, events: evts, terminal });
                    } else if (errorEv && waitKind !== 'error') {
                        clearTimeout(timer); clearInterval(poll); pending.delete(rid);
                        res({ ok: false, error: 'Error event', events: evts, terminal: errorEv });
                    }
                }, 50);
            });
        }

        // Store globally so page.evaluate can access it
        window.__zenith_ws = ws;
        window.__zenith_rpc = rpc;
        window.__zenith_stream = stream;
        window.__zenith_events = events;

        setTimeout(() => { if (connected) resolve(true); else reject(new Error('Not connected')); }, 100);
    });
}
"""


def start_backend() -> subprocess.Popen:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_fh = open(LOG_DIR / "backend_playwright.log", "w", encoding="utf-8")
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

    url = HEALTH_URL
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


async def run_tests(headless: bool, timeout: float):
    from playwright.async_api import async_playwright

    backend_proc = start_backend()
    results = {"passed": [], "failed": [], "warned": []}

    def ok(name):
        results["passed"].append(name)
        logging.info("  PASS  %s", name)

    def fail(name, reason=""):
        results["failed"].append(f"{name}: {reason}")
        logging.error("  FAIL  %s -- %s", name, reason)

    def warn(name, msg=""):
        results["warned"].append(f"{name}: {msg}")
        logging.warning("  WARN  %s -- %s", name, msg)

    try:
        logging.info("Waiting for backend...")
        if not await wait_for_backend(timeout):
            logging.error("Backend failed to start")
            return 1
        logging.info("Backend ready")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            page = await browser.new_page()

            # Navigate to the backend health endpoint to establish origin for WS
            await page.goto(HEALTH_URL)

            logging.info("")
            logging.info("--- HEALTH CHECK ---")
            import urllib.request

            try:
                req = urllib.request.Request(HEALTH_URL)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                    if data.get("status") == "ok":
                        ok("health")
                    else:
                        fail("health", str(data))
            except Exception as e:
                fail("health", str(e))

            # Open persistent WebSocket connection
            await page.evaluate(JS_SETUP, {"wsUrl": WS_URL})
            logging.info("WebSocket connected")

            def rpc(method, params=None, timeout=15):
                p = json.dumps(params or {})
                return page.evaluate(f"() => window.__zenith_rpc('{method}', {p}, {timeout})")

            def stream(method, params, wait_kind, timeout=90):
                p = json.dumps(params)
                return page.evaluate(
                    f"() => window.__zenith_stream('{method}', {p}, '{wait_kind}', {timeout})"
                )

            logging.info("")
            logging.info("--- SESSION LIFECYCLE ---")

            # Create session
            create_resp = await rpc("session.create", {"title": "Playwright E2E Test"})
            session_id = create_resp.get("result", {}).get("id")
            if session_id:
                ok("session.create")
            else:
                fail("session.create", str(create_resp))
                await page.evaluate("() => window.__zenith_ws.close()")
                await browser.close()
                return 1

            # List sessions
            list_resp = await rpc("session.list_all", {"limit": 5})
            sessions = list_resp.get("result", list_resp)
            if isinstance(sessions, list) and len(sessions) > 0:
                ok(f"session.list_all ({len(sessions)} sessions)")
            else:
                fail("session.list_all", str(list_resp))

            # Resume session
            resume_resp = await rpc("session.resume", {"session_id": session_id})
            if resume_resp.get("result"):
                ok("session.resume")
            else:
                fail("session.resume", str(resume_resp))

            logging.info("")
            logging.info("--- PROMPT FLOW: Basic Response ---")

            # Send a prompt and stream all events until success
            try:
                stream_result = await stream(
                    "prompt.send",
                    {
                        "content": "What is 2+2? Reply with just the number.",
                        "mode": "build",
                        "session_id": session_id,
                    },
                    "success",
                    int(timeout),
                )
                ok("prompt.send.completed")
            except Exception as e:
                fail("prompt.send", str(e))
                stream_result = {"events": []}

            events = stream_result.get("events", [])
            event_kinds = [e["kind"] for e in events]

            logging.info("  Event kinds received: %s", event_kinds)
            logging.info("  Total events: %d", len(events))

            # Verify required event kinds
            for kind in ["message", "success"]:
                if kind in event_kinds:
                    ok(f"event.{kind}")
                else:
                    fail(f"event.{kind}", f"Not in {event_kinds}")

            # Verify optional event kinds
            for kind in [
                "turn_manifest",
                "thinking",
                "progress",
                "tool_call",
                "tool_result",
                "warning",
            ]:
                if kind in event_kinds:
                    ok(f"event.{kind}")
                else:
                    warn(f"event.{kind}", "Not emitted (may be normal)")

            # Verify streaming: check for partial messages
            partial_msgs = [
                e for e in events if e["kind"] == "message" and e.get("data", {}).get("partial")
            ]
            final_msgs = [
                e for e in events if e["kind"] == "message" and not e.get("data", {}).get("partial")
            ]
            if partial_msgs:
                ok(f"streaming.partials ({len(partial_msgs)} partial messages)")
            else:
                warn("streaming.partials", "No partial messages")
            if final_msgs:
                ok("streaming.final")
                final_text = final_msgs[0].get("data", {}).get("text", "")
                logging.info("  Response text: %.100s...", final_text)
            else:
                fail("streaming.final", "No final message")

            # Verify success event structure
            success_ev = next((e for e in events if e["kind"] == "success"), None)
            if success_ev:
                sd = success_ev.get("data", {})
                for field in ["message", "iterations", "elapsedMs"]:
                    if field in sd:
                        ok(f"success.{field}")
                    else:
                        fail(f"success.{field}", f"Missing from {list(sd.keys())}")

                ti = sd.get("tokenInfo", {})
                if ti:
                    ok("success.tokenInfo")
                    for field in ["used", "remaining", "total", "percent"]:
                        if field in ti:
                            ok(f"success.tokenInfo.{field}")
                        else:
                            fail(f"success.tokenInfo.{field}", f"Missing from {list(ti.keys())}")

                    if "stale_reads_evicted" in ti:
                        ok("success.stale_reads_evicted")
                    else:
                        warn("success.stale_reads_evicted", "Not in tokenInfo")
                    if "cache_hit_rate" in ti:
                        ok("success.cache_hit_rate")
                    else:
                        warn("success.cache_hit_rate", "Not in tokenInfo")
                    if "tierBreakdown" in ti or "tierBreakdown" in sd:
                        ok("success.tierBreakdown")
                    else:
                        warn("success.tierBreakdown", "Not found")
                else:
                    fail("success.tokenInfo", "No tokenInfo in success data")
            else:
                fail("success.event", "No success event found")

            # Verify turn_manifest structure
            manifest_ev = next((e for e in events if e["kind"] == "turn_manifest"), None)
            if manifest_ev:
                md = manifest_ev.get("data", {})
                for field in ["created", "modified", "remaining", "completed", "stalled"]:
                    if field in md:
                        ok(f"manifest.{field}")
                    else:
                        fail(f"manifest.{field}", f"Missing from {list(md.keys())}")
            else:
                warn("manifest.structure", "No turn_manifest event")

            # Verify message content is not empty
            if final_msgs:
                text = final_msgs[0].get("data", {}).get("text", "")
                if len(text) > 0:
                    ok(f"response.non_empty ({len(text)} chars)")
                else:
                    fail("response.non_empty", "Empty response")

            logging.info("")
            logging.info("--- PROMPT FLOW: Tool Use ---")

            tool_resp = await rpc("session.create", {"title": "Tool Test"})
            tool_sid = tool_resp.get("result", {}).get("id", "")

            try:
                tool_stream = await stream(
                    "prompt.send",
                    {
                        "content": "List all files in the current directory",
                        "mode": "build",
                        "session_id": tool_sid,
                    },
                    "success",
                    int(timeout),
                )
            except Exception as e:
                fail("tool_prompt", str(e))
                tool_stream = {"events": []}

            tool_events = tool_stream.get("events", [])
            tool_kinds = [e["kind"] for e in tool_events]
            logging.info("  Event kinds for tool prompt: %s", tool_kinds)

            if "tool_call" in tool_kinds:
                ok("tool_use.tool_call")
                tc = next(e for e in tool_events if e["kind"] == "tool_call")
                tcd = tc.get("data", {})
                for field in ["tool", "params"]:
                    if field in tcd:
                        ok(f"tool_use.tool_call.{field}")
                    else:
                        fail(f"tool_use.tool_call.{field}", f"Missing: {list(tcd.keys())}")
            else:
                warn("tool_use.tool_call", "No tool_call event (may not need tools)")

            if "tool_result" in tool_kinds:
                ok("tool_use.tool_result")
                tr = next(e for e in tool_events if e["kind"] == "tool_result")
                trd = tr.get("data", {})
                for field in ["tool", "success", "output"]:
                    if field in trd:
                        ok(f"tool_use.tool_result.{field}")
                    else:
                        fail(f"tool_use.tool_result.{field}", f"Missing: {list(trd.keys())}")
            else:
                warn("tool_use.tool_result", "No tool_result event")

            logging.info("")
            logging.info("--- CONTEXT OPERATIONS ---")

            compact_resp = await rpc("context.compact", {"session_id": session_id})
            if not compact_resp.get("error"):
                ok("context.compact")
            else:
                fail("context.compact", str(compact_resp.get("error")))

            clear_resp = await rpc("context.clear_tools", {"session_id": session_id})
            if not clear_resp.get("error"):
                ok("context.clear_tools")
            else:
                fail("context.clear_tools", str(clear_resp.get("error")))

            logging.info("")
            logging.info("--- PROVIDER OPERATIONS ---")

            validate_resp = await rpc("provider.validate", {"provider": "openrouter"}, 30)
            if not validate_resp.get("error"):
                ok("provider.validate")
            else:
                warn("provider.validate", str(validate_resp.get("error", {}).get("message", "")))

            models_resp = await rpc("provider.models", {"provider": "openrouter"})
            if not models_resp.get("error"):
                ok("provider.models")
            else:
                warn("provider.models", str(models_resp.get("error", {}).get("message", "")))

            logging.info("")
            logging.info("--- WORKSPACE OPERATIONS ---")

            for op, params in [
                ("workspace.status", {}),
                ("workspace.diff", {}),
                ("workspace.log", {"limit": 5}),
            ]:
                resp = await rpc(op, params)
                if not resp.get("error"):
                    ok(op)
                else:
                    warn(op, str(resp.get("error", {}).get("message", "")))

            logging.info("")
            logging.info("--- TOOLS & MEMORY ---")

            tools_resp = await rpc("tools.list", {})
            if not tools_resp.get("error"):
                ok("tools.list")
            else:
                fail("tools.list", str(tools_resp.get("error")))

            logging.info("")
            logging.info("--- SESSION DELETE ---")

            del_resp = await rpc("session.delete", {"session_id": session_id})
            if not del_resp.get("error"):
                ok("session.delete")
            else:
                fail("session.delete", str(del_resp.get("error")))

            # Clean up tool test session
            if tool_sid:
                await rpc("session.delete", {"session_id": tool_sid})

            await page.evaluate("() => window.__zenith_ws.close()")
            await browser.close()

        # Print summary
        logging.info("")
        logging.info("=" * 70)
        logging.info("PLAYWRIGHT E2E TEST RESULTS")
        logging.info("=" * 70)
        logging.info("  Passed:   %d", len(results["passed"]))
        logging.info("  Failed:   %d", len(results["failed"]))
        logging.info("  Warned:   %d", len(results["warned"]))
        logging.info("")
        if results["failed"]:
            logging.info("FAILURES:")
            for f in results["failed"]:
                logging.info("  - %s", f)
        if results["warned"]:
            logging.info("WARNINGS:")
            for w in results["warned"]:
                logging.info("  - %s", w)
        logging.info("=" * 70)

        # Save report
        report_file = LOG_DIR / f"playwright_report_{time.strftime('%Y%m%d_%H%M%S')}.json"
        report_file.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        logging.info("Report saved: %s", report_file)

        return 1 if results["failed"] else 0

    finally:
        logging.info("Shutting down backend (PID %d)...", backend_proc.pid)
        try:
            backend_proc.terminate()
            backend_proc.wait(timeout=5)
        except Exception:
            backend_proc.kill()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--headless", type=str, default="true")
    args = parser.parse_args()
    headless = args.headless.lower() != "false"
    sys.exit(asyncio.run(run_tests(headless, args.timeout)))


if __name__ == "__main__":
    main()
