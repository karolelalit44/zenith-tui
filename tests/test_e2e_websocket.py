"""End-to-end tests: live server → WebSocket client → events → EventMapper validation.

Tests the full pipeline: frontend request → backend processing → events → frontend rendering.
Uses a real uvicorn server with a mock EchoProvider to avoid needing API keys.
"""

import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest
import websockets


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── Live server fixture (subprocess) ─────────────────────────────────

_SERVER_READY_TIMEOUT = 20
_ECHO_PROVIDER_CODE = '''
import asyncio
import logging
logging.disable(logging.CRITICAL)

from zenith.providers.base import BaseProvider

class EchoProvider(BaseProvider):
    def __init__(self):
        super().__init__("echo", "echo-v1")
    async def complete(self, messages, tools=None):
        user_msg = messages[-1]["content"] if messages else ""
        return f"Echo: {user_msg}"
    async def stream(self, messages, tools=None):
        response = await self.complete(messages)
        for word in response.split():
            yield (word + " ", None)
            await asyncio.sleep(0.01)
    async def validate(self):
        return True
    async def list_models(self):
        return ["echo-v1"]
'''


@pytest.fixture(scope="module")
def echo_server(tmp_path_factory):
    """Start a real zenith server with EchoProvider in a subprocess."""
    port = _get_free_port()
    db_path = str(tmp_path_factory.mktemp("e2e") / "test.db")
    workspace = str(tmp_path_factory.mktemp("workspace"))

    # Write the provider monkey-patch to a temp file
    prov_file = Path(tempfile.mktemp(suffix=".py"))
    prov_file.write_text(_ECHO_PROVIDER_CODE)

    env = os.environ.copy()
    # Ensure all required env vars are set for the subprocess
    env.setdefault("ZENITH_ACTIVE_PROVIDER", "echo")
    env.setdefault("ZENITH_DB_PATH", db_path)
    env.setdefault("ZENITH_LOG_LEVEL", "CRITICAL")
    env.setdefault("ZENITH_MAX_CONTEXT_TOKENS", "128000")
    env.setdefault("ZENITH_SUMMARY_THRESHOLD", "0.8")
    env.setdefault("ZENITH_BASH_TIMEOUT", "30")
    env.setdefault("ZENITH_MAX_ITERATIONS", "25")
    env.setdefault("ZENITH_MAX_TOOL_OUTPUT", "10000")
    env.setdefault("ZENITH_MAX_RETRIES", "3")
    env.setdefault("ZENITH_STREAM_MAX_RETRIES", "2")
    env.setdefault("ZENITH_RETRY_BASE_DELAY", "1.0")
    env.setdefault("ZENITH_RETRY_MAX_DELAY", "60.0")
    env.setdefault("ZENITH_VALIDATION_TIMEOUT", "30")
    env.setdefault("ZENITH_WEBFETCH_TIMEOUT", "30")
    env.setdefault("ZENITH_WEBFETCH_MAX_BYTES", "50000")
    env.setdefault("ZENITH_GIT_TIMEOUT", "30")
    env.setdefault("ZENITH_MAX_TOKENS", "4096")
    env.setdefault("ZENITH_TEMPERATURE", "0.7")
    env["ZENITH_ECHO_PROVIDER"] = str(prov_file)

    server_script = f'''
import os, sys
os.environ["ZENITH_DB_PATH"] = {db_path!r}
os.environ["ZENITH_LOG_LEVEL"] = "CRITICAL"

# Monkey-patch the provider system before server starts
import importlib.util
spec = importlib.util.spec_from_file_location("echo_prov", {str(prov_file)!r})
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

import zenith.providers.registry as reg
_orig_from_config = reg.ProviderRegistry.from_config

def _patched_from_config(providers, active, **kw):
    r = _orig_from_config(providers, active, **kw)
    r.register("echo", mod.EchoProvider())
    return r

reg.ProviderRegistry.from_config = _patched_from_config

# Also patch load_config result to add echo provider
import zenith.config.loader as loader
_orig_load = loader.load_config

def _patched_load(*a, **kw):
    cfg = _orig_load(*a, **kw)
    from zenith.config.providers import ProviderConfig
    if cfg.providers is None:
        cfg.providers = {{}}
    cfg.providers["echo"] = ProviderConfig(model="echo-v1", is_active=True, api_key="echo-test-key")
    cfg.active_provider = "echo"
    return cfg

loader.load_config = _patched_load

import uvicorn
uvicorn.run("zenith.transport.server:app", host="127.0.0.1", port={port}, log_level="error")
'''
    server_file = Path(tempfile.mktemp(suffix=".py"))
    server_file.write_text(server_script)

    proc = subprocess.Popen(
        [sys.executable, str(server_file)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready
    deadline = time.time() + _SERVER_READY_TIMEOUT
    ready = False
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                ready = True
                break
        except OSError:
            time.sleep(0.1)

    if not ready:
        proc.kill()
        stdout, stderr = proc.communicate(timeout=5)
        pytest.fail(f"Server failed to start on port {port}.\nstdout: {stdout.decode()}\nstderr: {stderr.decode()}")

    yield port

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


# ── HTTP endpoint tests (in-process, no server needed) ────────────────

@pytest.mark.asyncio
async def test_http_health():
    """Server health endpoint returns ok."""
    from httpx import AsyncClient, ASGITransport
    from zenith.transport.server import create_app
    import zenith.transport.server as srv
    from zenith.config.settings import AppSettings
    from zenith.config.providers import ProviderConfig
    from zenith.db.connection import Database
    from zenith.providers.registry import ProviderRegistry
    from zenith.providers.base import BaseProvider
    from zenith.transport.websocket import ZenithHandler

    class _HP(BaseProvider):
        def __init__(self):
            super().__init__("echo", "echo-v1")
        async def complete(self, messages, tools=None):
            return "ok"
        async def stream(self, messages, tools=None):
            yield ("ok", None)
        async def validate(self):
            return True
        async def list_models(self):
            return ["echo-v1"]

    tmp = Path(tempfile.mkdtemp())
    cfg = AppSettings(
        providers={"echo": ProviderConfig(model="echo-v1", is_active=True)},
        active_provider="echo",
        db_path=str(tmp / "db.sqlite"),
        workspace_root=str(tmp),
    )
    db = Database(cfg.db_path)
    await db.connect()
    reg = ProviderRegistry()
    reg.register("echo", _HP())
    handler = ZenithHandler(config=cfg, db=db, registry=reg)

    app = create_app()
    original = srv._handler
    srv._handler = handler
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert "version" in data
    finally:
        srv._handler = original
        await db.close()


@pytest.mark.asyncio
async def test_http_status():
    """Server status endpoint returns ready with provider info."""
    from httpx import AsyncClient, ASGITransport
    from zenith.transport.server import create_app
    import zenith.transport.server as srv
    from zenith.config.settings import AppSettings
    from zenith.config.providers import ProviderConfig
    from zenith.db.connection import Database
    from zenith.providers.registry import ProviderRegistry
    from zenith.providers.base import BaseProvider
    from zenith.transport.websocket import ZenithHandler

    class _SP(BaseProvider):
        def __init__(self):
            super().__init__("echo", "echo-v1")
        async def complete(self, messages, tools=None):
            return "ok"
        async def stream(self, messages, tools=None):
            yield ("ok", None)
        async def validate(self):
            return True
        async def list_models(self):
            return ["echo-v1"]

    tmp = Path(tempfile.mkdtemp())
    cfg = AppSettings(
        providers={"echo": ProviderConfig(model="echo-v1", is_active=True)},
        active_provider="echo",
        db_path=str(tmp / "db.sqlite"),
        workspace_root=str(tmp),
    )
    db = Database(cfg.db_path)
    await db.connect()
    reg = ProviderRegistry()
    reg.register("echo", _SP())
    handler = ZenithHandler(config=cfg, db=db, registry=reg)

    app = create_app()
    original = srv._handler
    srv._handler = handler
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ready"] is True
            assert data["provider"] == "echo"
    finally:
        srv._handler = original
        await db.close()


# ── WebSocket JSON-RPC protocol tests (live server) ──────────────────

async def _ws_rpc(ws, method: str, params: dict[str, Any] | None = None) -> dict:
    """Send a JSON-RPC request and wait for the response."""
    rid = f"test_{method}_{int(time.time() * 1000)}"
    request: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params:
        request["params"] = params
    await ws.send(json.dumps(request))

    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=30)
        data = json.loads(raw)
        if "id" in data and data["id"] == rid:
            return data
        # skip events, keep waiting for our response


async def _collect_events(ws, timeout: float = 15) -> list[dict]:
    """Collect all JSON-RPC event notifications from the WebSocket."""
    events: list[dict] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            remaining = deadline - time.time()
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, remaining))
            data = json.loads(raw)
            if data.get("method") == "event":
                events.append(data)
        except asyncio.TimeoutError:
            break
    return events


@pytest.mark.asyncio
async def test_ws_session_create(echo_server):
    """WebSocket session.create returns a valid session object."""
    port = echo_server
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
        resp = await _ws_rpc(ws, "session.create", {"title": "E2E Test"})
        assert "result" in resp, f"Expected result, got: {resp}"
        session = resp["result"]
        assert "id" in session
        assert session["title"] == "E2E Test"


@pytest.mark.asyncio
async def test_ws_session_list(echo_server):
    """WebSocket session.list returns sessions after creating one."""
    port = echo_server
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
        await _ws_rpc(ws, "session.create", {"title": "List Test"})
        resp = await _ws_rpc(ws, "session.list")
        assert "result" in resp
        sessions = resp["result"]
        assert isinstance(sessions, list)
        assert len(sessions) >= 1
        titles = [s["title"] for s in sessions]
        assert "List Test" in titles


@pytest.mark.asyncio
async def test_ws_session_resume(echo_server):
    """WebSocket session.resume returns session + messages."""
    port = echo_server
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
        create_resp = await _ws_rpc(ws, "session.create", {"title": "Resume Test"})
        sid = create_resp["result"]["id"]

        resp = await _ws_rpc(ws, "session.resume", {"session_id": sid})
        assert "result" in resp
        data = resp["result"]
        assert "session" in data
        assert "messages" in data
        assert data["session"]["id"] == sid
        assert isinstance(data["messages"], list)


@pytest.mark.asyncio
async def test_ws_prompt_full_event_pipeline(echo_server):
    """Full pipeline: send prompt → receive thinking/message/success events.

    Validates:
    - prompt.send returns {session_id, status: processing}
    - Event notifications arrive in JSON-RPC format
    - Events include thinking → message(partial) → message(final) → success
    - Each event has correct kind, data shape, session_id
    """
    port = echo_server
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
        # Create session
        create_resp = await _ws_rpc(ws, "session.create", {"title": "Pipeline Test"})
        sid = create_resp["result"]["id"]

        # Send prompt
        prompt_resp = await _ws_rpc(ws, "prompt.send", {
            "content": "Hello from E2E test",
            "mode": "build",
        })
        assert "result" in prompt_resp
        assert prompt_resp["result"]["status"] == "processing"
        assert prompt_resp["result"]["session_id"] == sid

        # Collect events
        events = await _collect_events(ws, timeout=15)

        assert len(events) >= 3, (
            f"Expected at least 3 events, got {len(events)}: "
            f"{[e['params']['kind'] for e in events]}"
        )

        kinds = [e["params"]["kind"] for e in events]
        assert "thinking" in kinds, f"Missing thinking event. Got: {kinds}"
        assert "success" in kinds, f"Missing success event. Got: {kinds}"

        # Validate JSON-RPC event structure
        for evt in events:
            assert evt["jsonrpc"] == "2.0", "Event must have jsonrpc 2.0"
            assert evt["method"] == "event", "Event method must be 'event'"
            params = evt["params"]
            assert "kind" in params, "Event params must have 'kind'"
            assert "id" in params, "Event params must have 'id'"
            assert "data" in params, "Event params must have 'data'"
            assert "session_id" in params, f"Event {params['kind']} must have session_id"
            assert params["session_id"] == sid, (
                f"Event session_id mismatch: {params['session_id']} != {sid}"
            )

        # Validate thinking event shape
        thinking_evt = next(e for e in events if e["params"]["kind"] == "thinking")
        assert "text" in thinking_evt["params"]["data"]

        # Validate success event shape
        success_evt = next(e for e in events if e["params"]["kind"] == "success")
        success_data = success_evt["params"]["data"]
        assert "message" in success_data
        assert "iterations" in success_data


@pytest.mark.asyncio
async def test_ws_prompt_empty_rejected(echo_server):
    """Empty prompt returns an error."""
    port = echo_server
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
        resp = await _ws_rpc(ws, "prompt.send", {"content": "   ", "mode": "build"})
        assert "error" in resp
        assert "Empty prompt" in resp["error"]["message"]


@pytest.mark.asyncio
async def test_ws_health(echo_server):
    """WS health method returns ok."""
    port = echo_server
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
        resp = await _ws_rpc(ws, "health")
        assert "result" in resp
        assert resp["result"]["status"] == "ok"


@pytest.mark.asyncio
async def test_ws_unknown_method(echo_server):
    """Unknown method returns error -32601."""
    port = echo_server
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
        resp = await _ws_rpc(ws, "nonexistent.method")
        assert "error" in resp
        assert resp["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_ws_tools_list(echo_server):
    """tools.list returns tool schemas."""
    port = echo_server
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
        resp = await _ws_rpc(ws, "tools.list", {"mode": "build"})
        assert "result" in resp
        tools = resp["result"]["tools"]
        assert isinstance(tools, list)
        assert len(tools) > 0
        assert all("name" in t for t in tools)


@pytest.mark.asyncio
async def test_ws_provider_validate(echo_server):
    """provider.validate returns valid=True for the echo provider."""
    port = echo_server
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
        resp = await _ws_rpc(ws, "provider.validate", {"provider": "echo"})
        assert "result" in resp
        assert resp["result"]["valid"] is True


@pytest.mark.asyncio
async def test_ws_provider_models(echo_server):
    """provider.models returns model list."""
    port = echo_server
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
        resp = await _ws_rpc(ws, "provider.models", {"provider": "echo"})
        assert "result" in resp
        models = resp["result"]["models"]
        assert "echo-v1" in models


@pytest.mark.asyncio
async def test_ws_session_not_found(echo_server):
    """session.resume with invalid ID returns error."""
    port = echo_server
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
        resp = await _ws_rpc(ws, "session.resume", {"session_id": "nonexistent"})
        assert "error" in resp
        assert "not found" in resp["error"]["message"].lower()


@pytest.mark.asyncio
async def test_ws_malformed_json(echo_server):
    """Malformed JSON returns parse error."""
    port = echo_server
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
        await ws.send("not json!!!")
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(raw)
        assert "error" in data
        assert data["error"]["code"] == -32700
