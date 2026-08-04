
import asyncio
import json
import os
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


async def _ws_rpc(ws, method: str, params: dict[str, Any] | None = None) -> dict:
    rid = f"e2e_{method}_{int(time.time() * 1000000)}"
    request: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params:
        request["params"] = params
    await ws.send(json.dumps(request))
    deadline = time.time() + 30
    while time.time() < deadline:
        raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.time()))
        data = json.loads(raw)
        if "id" in data and data["id"] == rid:
            return data
    raise TimeoutError(f"No response for method={method} id={rid}")


async def _collect_events(ws, timeout: float = 15) -> list[dict]:
    events: list[dict] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            remaining = deadline - time.time()
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, remaining))
            data = json.loads(raw)
            if data.get("method") == "event":
                events.append(data)
        except TimeoutError:
            break
    return events


async def _collect_all(ws, timeout: float = 5) -> list[dict]:
    messages: list[dict] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            remaining = deadline - time.time()
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, remaining))
            data = json.loads(raw)
            messages.append(data)
        except TimeoutError:
            break
    return messages


async def _send_prompt_and_collect(ws, content: str, mode: str = "build", timeout: float = 15) -> tuple[dict, list[dict]]:
    prompt_resp = await _ws_rpc(ws, "prompt.send", {"content": content, "mode": mode})
    events = await _collect_events(ws, timeout=timeout)
    return prompt_resp, events



_ECHO_PROVIDER_CODE = """
import asyncio
import logging
logging.disable(logging.CRITICAL)
from server.providers.base import BaseProvider

class EchoProvider(BaseProvider):
    def __init__(self):
        super().__init__("echo", "echo-v1")
    async def complete(self, messages, tools=None):
        user_msg = messages[-1]["content"] if messages else ""
        return f"Echo: {user_msg}"
    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        response = await self.complete(messages)
        for word in response.split():
            yield (word + " ", None)
            await asyncio.sleep(0.01)
    async def validate(self):
        return True
    async def list_models(self):
        return ["echo-v1"]
"""

_SERVER_READY_TIMEOUT = 20


@pytest.fixture(scope="module")
def echo_server(tmp_path_factory):
    port = _get_free_port()
    db_path = str(tmp_path_factory.mktemp("e2e") / "test.db")
    str(tmp_path_factory.mktemp("workspace"))

    prov_file = Path(tempfile.mktemp(suffix=".py"))
    prov_file.write_text(_ECHO_PROVIDER_CODE)

    env = os.environ.copy()
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

    server_script = f"""
import os, sys
os.environ["ZENITH_DB_PATH"] = {db_path!r}
os.environ["ZENITH_LOG_LEVEL"] = "CRITICAL"

import importlib.util
spec = importlib.util.spec_from_file_location("echo_prov", {str(prov_file)!r})
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
import server.providers.registry as reg
_orig_from_config = reg.ProviderRegistry.from_config

def _patched_from_config(providers, active, **kw):
    r = _orig_from_config(providers, active, **kw)
    r.register("echo", mod.EchoProvider())
    return r

reg.ProviderRegistry.from_config = _patched_from_config

import server.config.loader as loader
_orig_load = loader.load_config

def _patched_load(*a, **kw):
    cfg = _orig_load(*a, **kw)
    from server.config.providers import ProviderConfig
    if cfg.providers is None:
        cfg.providers = {{}}
    cfg.providers["echo"] = ProviderConfig(model="echo-v1", is_active=True, api_key="echo-test-key")
    cfg.active_provider = "echo"
    return cfg

loader.load_config = _patched_load

import uvicorn
uvicorn.run("transport.server:app", host="127.0.0.1", port={port}, log_level="error")
"""
    server_file = Path(tempfile.mktemp(suffix=".py"))
    server_file.write_text(server_script)

    proc = subprocess.Popen([sys.executable, str(server_file)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

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




class TestHTTPEndpoints:

    def test_health_returns_ok_with_version(self, echo_server):
        import urllib.request

        resp = urllib.request.urlopen(f"http://127.0.0.1:{echo_server}/health")
        data = json.loads(resp.read())
        assert data["status"] == "ok"
        assert "version" in data
        assert isinstance(data["version"], str)
        assert data["handler"] is True

    def test_status_returns_ready_with_provider_info(self, echo_server):
        import urllib.request

        resp = urllib.request.urlopen(f"http://127.0.0.1:{echo_server}/status")
        data = json.loads(resp.read())
        assert data["ready"] is True
        assert data["provider"] == "echo"
        assert isinstance(data["tools"], list)
        assert len(data["tools"]) > 0

    def test_startup_validate_endpoint(self, echo_server):
        import urllib.request

        resp = urllib.request.urlopen(f"http://127.0.0.1:{echo_server}/startup/validate")
        data = json.loads(resp.read())
        assert "status" in data
        assert "missing" in data




class TestWSProtocol:

    @pytest.mark.asyncio
    async def test_ws_health(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "health")
            assert "result" in resp
            assert resp["result"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_ws_unknown_method_returns_32601(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "nonexistent.method")
            assert "error" in resp
            assert resp["error"]["code"] == -32601
            assert "not found" in resp["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_ws_malformed_json_returns_parse_error(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await ws.send("not json!!!{{{")
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(raw)
            assert "error" in data
            assert data["error"]["code"] == -32700

    @pytest.mark.asyncio
    async def test_ws_empty_object_returns_error(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await ws.send("{}")
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(raw)
            assert "error" in data

    @pytest.mark.asyncio
    async def test_ws_multiple_rpcs_on_same_connection(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            r1 = await _ws_rpc(ws, "health")
            r2 = await _ws_rpc(ws, "tools.list", {"mode": "build"})
            r3 = await _ws_rpc(ws, "health")
            assert r1["result"]["status"] == "ok"
            assert len(r2["result"]["tools"]) > 0
            assert r3["result"]["status"] == "ok"




class TestSessionManagement:

    @pytest.mark.asyncio
    async def test_session_create(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "session.create", {"title": "Test Session"})
            assert "result" in resp
            session = resp["result"]
            assert "id" in session
            assert session["title"] == "Test Session"
            assert isinstance(session["id"], str)
            assert len(session["id"]) > 0

    @pytest.mark.asyncio
    async def test_session_list_after_create(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await _ws_rpc(ws, "session.create", {"title": "List Me"})
            resp = await _ws_rpc(ws, "session.list")
            assert "result" in resp
            sessions = resp["result"]
            assert isinstance(sessions, list)
            titles = [s["title"] for s in sessions]
            assert "List Me" in titles

    @pytest.mark.asyncio
    async def test_session_list_multiple_sessions(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await _ws_rpc(ws, "session.create", {"title": "Multi A"})
            await _ws_rpc(ws, "session.create", {"title": "Multi B"})
            resp = await _ws_rpc(ws, "session.list")
            sessions = resp["result"]
            titles = [s["title"] for s in sessions]
            assert "Multi A" in titles
            assert "Multi B" in titles

    @pytest.mark.asyncio
    async def test_session_resume_returns_session_and_messages(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            create_resp = await _ws_rpc(ws, "session.create", {"title": "Resume Me"})
            sid = create_resp["result"]["id"]
            resp = await _ws_rpc(ws, "session.resume", {"session_id": sid})
            assert "result" in resp
            data = resp["result"]
            assert "session" in data
            assert "messages" in data
            assert data["session"]["id"] == sid
            assert isinstance(data["messages"], list)

    @pytest.mark.asyncio
    async def test_session_resume_not_found_returns_error(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "session.resume", {"session_id": "nonexistent-id"})
            assert "error" in resp
            assert "not found" in resp["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_session_create_default_title(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "session.create", {})
            assert "result" in resp
            assert resp["result"]["title"] == "New Session"




class TestPromptProcessing:

    @pytest.mark.asyncio
    async def test_prompt_returns_processing_status(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await _ws_rpc(ws, "session.create", {"title": "Prompt Test"})
            resp = await _ws_rpc(ws, "prompt.send", {"content": "Hello", "mode": "build"})
            assert "result" in resp
            assert resp["result"]["status"] == "processing"
            assert "session_id" in resp["result"]
            await _collect_events(ws, timeout=3)

    @pytest.mark.asyncio
    async def test_prompt_empty_rejected(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "prompt.send", {"content": "   ", "mode": "build"})
            assert "error" in resp
            assert "Empty prompt" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_prompt_generates_thinking_event(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await _ws_rpc(ws, "session.create", {"title": "Thinking Test"})
            await _ws_rpc(ws, "prompt.send", {"content": "What is 2+2?", "mode": "build"})
            events = await _collect_events(ws, timeout=10)
            kinds = [e["params"]["kind"] for e in events]
            assert "thinking" in kinds, f"Missing thinking event. Got: {kinds}"

    @pytest.mark.asyncio
    async def test_prompt_generates_message_events(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await _ws_rpc(ws, "session.create", {"title": "Message Test"})
            await _ws_rpc(ws, "prompt.send", {"content": "Say hello", "mode": "build"})
            events = await _collect_events(ws, timeout=10)
            message_events = [e for e in events if e["params"]["kind"] == "message"]
            assert len(message_events) > 0, (f"No message events. Got: {[e['params']['kind'] for e in events]}")

    @pytest.mark.asyncio
    async def test_prompt_generates_success_event(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await _ws_rpc(ws, "session.create", {"title": "Success Test"})
            await _ws_rpc(ws, "prompt.send", {"content": "Done?", "mode": "build"})
            events = await _collect_events(ws, timeout=10)
            success_events = [e for e in events if e["params"]["kind"] == "success"]
            assert len(success_events) > 0
            success_data = success_events[0]["params"]["data"]
            assert "message" in success_data
            assert "iterations" in success_data

    @pytest.mark.asyncio
    async def test_prompt_event_session_ids_match(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            create_resp = await _ws_rpc(ws, "session.create", {"title": "Session ID Match"})
            sid = create_resp["result"]["id"]
            await _ws_rpc(ws, "prompt.send", {"content": "Verify session", "mode": "build"})
            events = await _collect_events(ws, timeout=10)
            for evt in events:
                assert evt["params"]["session_id"] == sid, (f"Event {evt['params']['kind']} session_id={evt['params']['session_id']} != {sid}")

    @pytest.mark.asyncio
    async def test_prompt_event_jsonrpc_structure(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await _ws_rpc(ws, "session.create", {"title": "JSON-RPC Structure"})
            await _ws_rpc(ws, "prompt.send", {"content": "Structure check", "mode": "build"})
            events = await _collect_events(ws, timeout=10)
            for evt in events:
                assert evt["jsonrpc"] == "2.0"
                assert evt["method"] == "event"
                params = evt["params"]
                assert "kind" in params
                assert "id" in params
                assert "data" in params
                assert "session_id" in params
                assert "timestamp" in params

    @pytest.mark.asyncio
    async def test_prompt_echo_response_contains_input(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await _ws_rpc(ws, "session.create", {"title": "Echo Verify"})
            await _ws_rpc(ws, "prompt.send", {"content": "unique_marker_xyz", "mode": "build"})
            events = await _collect_events(ws, timeout=10)
            message_events = [e for e in events if e["params"]["kind"] == "message"]
            final_msgs = [e for e in message_events if not e["params"]["data"].get("partial")]
            assert len(final_msgs) > 0
            text = final_msgs[0]["params"]["data"].get("text", "")
            assert "unique_marker_xyz" in text




class TestMultiTurnConversation:

    @pytest.mark.asyncio
    async def test_two_prompts_same_session_history_accumulates(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            create_resp = await _ws_rpc(ws, "session.create", {"title": "Multi-Turn"})
            sid = create_resp["result"]["id"]

            await _ws_rpc(ws, "prompt.send", {"content": "First message", "mode": "build"})
            events1 = await _collect_events(ws, timeout=10)

            await _ws_rpc(ws, "prompt.send", {"content": "Second message", "mode": "build"})
            events2 = await _collect_events(ws, timeout=10)

            success1 = [e for e in events1 if e["params"]["kind"] == "success"]
            success2 = [e for e in events2 if e["params"]["kind"] == "success"]
            assert len(success1) > 0, "First prompt had no success event"
            assert len(success2) > 0, "Second prompt had no success event"

            resume_resp = await _ws_rpc(ws, "session.resume", {"session_id": sid})
            messages = resume_resp["result"]["messages"]
            assert len(messages) >= 4, (f"Expected at least 4 messages (2 user + 2 assistant), got {len(messages)}")
            roles = [m["role"] for m in messages]
            assert roles.count("user") >= 2
            assert roles.count("assistant") >= 2

    @pytest.mark.asyncio
    async def test_session_list_shows_all_sessions(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await _ws_rpc(ws, "session.create", {"title": "Independent A"})
            await _ws_rpc(ws, "session.create", {"title": "Independent B"})
            resp = await _ws_rpc(ws, "session.list")
            titles = [s["title"] for s in resp["result"]]
            assert "Independent A" in titles
            assert "Independent B" in titles




class TestAutoSession:

    @pytest.mark.asyncio
    async def test_prompt_without_session_creates_one(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "prompt.send", {"content": "Auto session test", "mode": "build"})
            assert "result" in resp
            assert resp["result"]["status"] == "processing"
            sid = resp["result"]["session_id"]
            assert isinstance(sid, str)
            assert len(sid) > 0
            await _collect_events(ws, timeout=10)

            list_resp = await _ws_rpc(ws, "session.list")
            ids = [s["id"] for s in list_resp["result"]]
            assert sid in ids

    @pytest.mark.asyncio
    async def test_auto_session_title_from_prompt(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "prompt.send", {"content": "This is my custom title prompt", "mode": "build"})
            sid = resp["result"]["session_id"]
            await _collect_events(ws, timeout=10)
            resume = await _ws_rpc(ws, "session.resume", {"session_id": sid})
            title = resume["result"]["session"]["title"]
            assert title == "This is my custom title prompt"




class TestProviderOperations:

    @pytest.mark.asyncio
    async def test_provider_validate_echo(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "provider.validate", {"provider": "echo"})
            assert "result" in resp
            assert resp["result"]["valid"] is True

    @pytest.mark.asyncio
    async def test_provider_models_echo(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "provider.models", {"provider": "echo"})
            assert "result" in resp
            assert "echo-v1" in resp["result"]["models"]

    @pytest.mark.asyncio
    async def test_provider_validate_nonexistent(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "provider.validate", {"provider": "nonexistent"})
            assert "result" in resp
            assert resp["result"]["valid"] is False

    @pytest.mark.asyncio
    async def test_provider_models_nonexistent(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "provider.models", {"provider": "nonexistent"})
            assert "result" in resp
            assert resp["result"]["models"] == []




class TestToolOperations:

    @pytest.mark.asyncio
    async def test_tools_list_build_mode(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "tools.list", {"mode": "build"})
            assert "result" in resp
            tools = resp["result"]["tools"]
            assert isinstance(tools, list)
            assert len(tools) > 0
            names = [t["name"] for t in tools]
            assert "bash" in names
            assert "file_read" in names
            assert "file_write" in names
            assert "file_edit" in names
            assert "glob" in names
            assert "grep" in names

    @pytest.mark.asyncio
    async def test_tools_list_all_have_name(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "tools.list", {"mode": "build"})
            tools = resp["result"]["tools"]
            for tool in tools:
                assert "name" in tool, f"Tool missing 'name': {tool}"
                assert "description" in tool, f"Tool missing 'description': {tool}"

    @pytest.mark.asyncio
    async def test_tools_list_default_mode(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "tools.list", {})
            assert "result" in resp
            assert len(resp["result"]["tools"]) > 0




class TestSessionExport:

    @pytest.mark.asyncio
    async def test_session_export_after_prompt(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            create_resp = await _ws_rpc(ws, "session.create", {"title": "Export Test"})
            create_resp["result"]["id"]
            await _ws_rpc(ws, "prompt.send", {"content": "Export me", "mode": "build"})
            await _collect_events(ws, timeout=10)

            resp = await _ws_rpc(ws, "session.export", {"output_dir": "zenith_exports_e2e"})
            assert "result" in resp
            result = resp["result"]
            assert "filepath" in result
            assert "markdown" in result
            assert "# Export Test" in result["markdown"]

    @pytest.mark.asyncio
    async def test_session_export_no_session_returns_error(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "session.export", {})
            assert "error" in resp
            assert "no active session" in resp["error"]["message"].lower()




class TestWorkspaceOperations:

    @pytest.mark.asyncio
    async def test_workspace_status(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "workspace.status")
            assert "result" in resp
            data = resp["result"]
            if data.get("is_git_repo"):
                assert "branch" in data
                assert "modified" in data
                assert "staged" in data
                assert "untracked" in data
                assert "clean" in data

    @pytest.mark.asyncio
    async def test_workspace_diff(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "workspace.diff")
            assert "result" in resp
            assert "diff" in resp["result"]

    @pytest.mark.asyncio
    async def test_workspace_log(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "workspace.log", {"count": 5})
            assert "result" in resp
            assert "log" in resp["result"]
            assert isinstance(resp["result"]["log"], list)

    @pytest.mark.asyncio
    async def test_workspace_repo_map(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "workspace.repo_map", {"depth": 2})
            assert "result" in resp
            data = resp["result"]
            assert "structure" in data
            assert "summary" in data
            assert "keyFiles" in data




class TestConcurrentSessions:

    @pytest.mark.asyncio
    async def test_interleaved_prompts_different_sessions(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            s1 = await _ws_rpc(ws, "session.create", {"title": "Concurrent A"})
            s2 = await _ws_rpc(ws, "session.create", {"title": "Concurrent B"})
            sid1 = s1["result"]["id"]
            sid2 = s2["result"]["id"]
            assert sid1 != sid2

            await _ws_rpc(ws, "prompt.send", {"content": "From A", "mode": "build"})
            events_a = await _collect_events(ws, timeout=10)
            success_a = [e for e in events_a if e["params"]["kind"] == "success"]
            assert len(success_a) > 0

            await _ws_rpc(ws, "prompt.send", {"content": "From B", "mode": "build"})
            events_b = await _collect_events(ws, timeout=10)
            success_b = [e for e in events_b if e["params"]["kind"] == "success"]
            assert len(success_b) > 0

            list_resp = await _ws_rpc(ws, "session.list")
            ids = [s["id"] for s in list_resp["result"]]
            assert sid1 in ids
            assert sid2 in ids




class TestFullLifecycle:

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            health = await _ws_rpc(ws, "health")
            assert health["result"]["status"] == "ok"

            tools_resp = await _ws_rpc(ws, "tools.list", {"mode": "build"})
            assert len(tools_resp["result"]["tools"]) > 0

            prov_resp = await _ws_rpc(ws, "provider.validate", {"provider": "echo"})
            assert prov_resp["result"]["valid"] is True

            models_resp = await _ws_rpc(ws, "provider.models", {"provider": "echo"})
            assert "echo-v1" in models_resp["result"]["models"]

            create_resp = await _ws_rpc(ws, "session.create", {"title": "Lifecycle Test"})
            sid = create_resp["result"]["id"]

            prompt_resp = await _ws_rpc(ws, "prompt.send", {"content": "Do something amazing", "mode": "build"})
            assert prompt_resp["result"]["status"] == "processing"
            events = await _collect_events(ws, timeout=15)
            kinds = [e["params"]["kind"] for e in events]
            assert "thinking" in kinds
            assert "success" in kinds

            resume_resp = await _ws_rpc(ws, "session.resume", {"session_id": sid})
            messages = resume_resp["result"]["messages"]
            assert len(messages) >= 2
            roles = [m["role"] for m in messages]
            assert "user" in roles
            assert "assistant" in roles

            list_resp = await _ws_rpc(ws, "session.list")
            ids = [s["id"] for s in list_resp["result"]]
            assert sid in ids

            export_resp = await _ws_rpc(ws, "session.export", {"output_dir": "zenith_exports_lifecycle"})
            assert "markdown" in export_resp["result"]
            assert "Lifecycle Test" in export_resp["result"]["markdown"]

            ws_resp = await _ws_rpc(ws, "workspace.status")
            assert "result" in ws_resp




class TestErrorHandling:

    @pytest.mark.asyncio
    async def test_prompt_to_unavailable_provider(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "prompt.send", {"content": "Hello", "provider": "nonexistent_provider"})
            assert "error" in resp
            assert "not available" in resp["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_session_resume_after_second_ws_connect(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws1:
            create_resp = await _ws_rpc(ws1, "session.create", {"title": "Persistent Session"})
            sid = create_resp["result"]["id"]

        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws2:
            resume_resp = await _ws_rpc(ws2, "session.resume", {"session_id": sid})
            assert "result" in resume_resp
            assert resume_resp["result"]["session"]["id"] == sid

    @pytest.mark.asyncio
    async def test_jsonrpc_with_string_id(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            rid = "my_custom_id_123"
            request = {"jsonrpc": "2.0", "id": rid, "method": "health"}
            await ws.send(json.dumps(request))
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(raw)
            assert data["id"] == rid
            assert data["result"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_jsonrpc_with_integer_id(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            request = {"jsonrpc": "2.0", "id": 42, "method": "health"}
            await ws.send(json.dumps(request))
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(raw)
            assert data["id"] == 42

    @pytest.mark.asyncio
    async def test_prompt_with_special_characters(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await _ws_rpc(ws, "session.create", {"title": "Special Chars"})
            content = "Hello! @#$%^&*()_+-={}[]|\\:;'\"<>,.?/~`"
            await _ws_rpc(ws, "prompt.send", {"content": content, "mode": "build"})
            events = await _collect_events(ws, timeout=10)
            success = [e for e in events if e["params"]["kind"] == "success"]
            assert len(success) > 0

    @pytest.mark.asyncio
    async def test_prompt_with_long_content(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await _ws_rpc(ws, "session.create", {"title": "Long Prompt"})
            content = "A" * 5000
            await _ws_rpc(ws, "prompt.send", {"content": content, "mode": "build"})
            events = await _collect_events(ws, timeout=10)
            success = [e for e in events if e["params"]["kind"] == "success"]
            assert len(success) > 0

    @pytest.mark.asyncio
    async def test_prompt_with_unicode_content(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await _ws_rpc(ws, "session.create", {"title": "Unicode"})
            content = "Hello world 你好世界 مرحبا Здравствуйte"
            await _ws_rpc(ws, "prompt.send", {"content": content, "mode": "build"})
            events = await _collect_events(ws, timeout=10)
            message_events = [e for e in events if e["params"]["kind"] == "message"]
            assert len(message_events) > 0

    @pytest.mark.asyncio
    async def test_rapid_fire_requests(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            for i in range(5):
                request = {"jsonrpc": "2.0", "id": f"rapid_{i}", "method": "health"}
                await ws.send(json.dumps(request))

            responses = []
            deadline = time.time() + 10
            while len(responses) < 5 and time.time() < deadline:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.time()))
                data = json.loads(raw)
                if "id" in data:
                    responses.append(data)

            assert len(responses) == 5
            for resp in responses:
                assert resp["result"]["status"] == "ok"




class TestDataPersistence:

    @pytest.mark.asyncio
    async def test_session_messages_persist(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            create_resp = await _ws_rpc(ws, "session.create", {"title": "Persist Test"})
            sid = create_resp["result"]["id"]

            await _ws_rpc(ws, "prompt.send", {"content": "Persistent data", "mode": "build"})
            await _collect_events(ws, timeout=10)

        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws2:
            resume = await _ws_rpc(ws2, "session.resume", {"session_id": sid})
            messages = resume["result"]["messages"]
            assert len(messages) >= 2
            contents = [m["content"] for m in messages]
            assert any("Persistent data" in c for c in contents)

    @pytest.mark.asyncio
    async def test_multiple_sessions_persist_independently(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            s1 = await _ws_rpc(ws, "session.create", {"title": "Persist A"})
            s2 = await _ws_rpc(ws, "session.create", {"title": "Persist B"})
            sid1, sid2 = s1["result"]["id"], s2["result"]["id"]

            await _ws_rpc(ws, "session.resume", {"session_id": sid1})
            await _ws_rpc(ws, "prompt.send", {"content": "Message for A", "mode": "build"})
            await _collect_events(ws, timeout=10)

            await _ws_rpc(ws, "session.resume", {"session_id": sid2})
            await _ws_rpc(ws, "prompt.send", {"content": "Message for B", "mode": "build"})
            await _collect_events(ws, timeout=10)

        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws2:
            r1 = await _ws_rpc(ws2, "session.resume", {"session_id": sid1})
            r2 = await _ws_rpc(ws2, "session.resume", {"session_id": sid2})
            assert any("Message for A" in m["content"] for m in r1["result"]["messages"])
            assert any("Message for B" in m["content"] for m in r2["result"]["messages"])




class TestConnectionLifecycle:

    @pytest.mark.asyncio
    async def test_clean_disconnect_reconnect(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "health")
            assert resp["result"]["status"] == "ok"

        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            resp = await _ws_rpc(ws, "health")
            assert resp["result"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_disconnect_does_not_corrupt_server(self, echo_server):
        ws = await websockets.connect(f"ws://127.0.0.1:{echo_server}/ws")
        await _ws_rpc(ws, "health")
        await ws.close()

        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws2:
            resp = await _ws_rpc(ws2, "health")
            assert resp["result"]["status"] == "ok"




class TestModeHandling:

    @pytest.mark.asyncio
    async def test_build_mode_prompt(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await _ws_rpc(ws, "session.create", {"title": "Build Mode"})
            await _ws_rpc(ws, "prompt.send", {"content": "Build test", "mode": "build"})
            events = await _collect_events(ws, timeout=10)
            success = [e for e in events if e["params"]["kind"] == "success"]
            assert len(success) > 0

    @pytest.mark.asyncio
    async def test_chat_mode_prompt(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await _ws_rpc(ws, "session.create", {"title": "Chat Mode"})
            await _ws_rpc(ws, "prompt.send", {"content": "Chat test", "mode": "chat"})
            events = await _collect_events(ws, timeout=10)
            success = [e for e in events if e["params"]["kind"] == "success"]
            assert len(success) > 0

    @pytest.mark.asyncio
    async def test_default_mode_prompt(self, echo_server):
        async with websockets.connect(f"ws://127.0.0.1:{echo_server}/ws") as ws:
            await _ws_rpc(ws, "session.create", {"title": "Default Mode"})
            await _ws_rpc(ws, "prompt.send", {"content": "Default mode test"})
            events = await _collect_events(ws, timeout=10)
            success = [e for e in events if e["params"]["kind"] == "success"]
            assert len(success) > 0
