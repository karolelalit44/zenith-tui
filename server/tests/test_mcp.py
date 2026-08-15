from __future__ import annotations

import json
import os
import sys
import textwrap

import pytest

from server.config.loader import load_config
from server.config.settings import McpServerConfig
from server.mcp.client import McpClient
from server.mcp.manager import McpManager
from server.toolkit.registry import ToolRegistry

STUB_SERVER = '\nimport json\nimport sys\n\ndef read_message():\n    header = {}\n    while True:\n        line = sys.stdin.buffer.readline()\n        if not line:\n            return None\n        if line.strip() == b"":\n            break\n        k, _, v = line.decode().partition(":")\n        header[k.strip().lower()] = v.strip()\n    length = int(header.get("content-length", 0))\n    if length == 0:\n        return None\n    return json.loads(sys.stdin.buffer.read(length))\n\ndef write_message(msg):\n    body = json.dumps(msg).encode()\n    sys.stdout.buffer.write(f"Content-Length: {len(body)}\\r\\n\\r\\n".encode() + body)\n    sys.stdout.buffer.flush()\n\nwhile True:\n    msg = read_message()\n    if msg is None:\n        break\n    method = msg.get("method")\n    if method == "initialize":\n        write_message({"jsonrpc": "2.0", "id": msg["id"], "result": {\n            "protocolVersion": "2024-11-05",\n            "capabilities": {"tools": {}},\n            "serverInfo": {"name": "stub", "version": "1.0.0"},\n        }})\n    elif method == "notifications/initialized":\n        continue\n    elif method == "tools/list":\n        write_message({"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": [\n            {"name": "echo", "description": "Echoes input",\n             "inputSchema": {"type": "object",\n                             "properties": {"text": {"type": "string"}},\n                             "required": ["text"]}},\n            {"name": "failing", "description": "Always errors",\n             "inputSchema": {"type": "object", "properties": {}}},\n        ]}})\n    elif method == "tools/call":\n        name = msg["params"]["name"]\n        args = msg["params"]["arguments"]\n        if name == "failing":\n            write_message({"jsonrpc": "2.0", "id": msg["id"], "result": {\n                "content": [{"type": "text", "text": "boom"}], "isError": True,\n            }})\n        else:\n            write_message({"jsonrpc": "2.0", "id": msg["id"], "result": {\n                "content": [{"type": "text", "text": args.get("text", "")}], "isError": False,\n            }})\n    else:\n        write_message({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "not found"}})\n'


def write_stub_server(path):
    path.write_text(textwrap.dedent(STUB_SERVER))
    return str(path)


def make_config(tmp_path) -> McpServerConfig:
    return McpServerConfig(
        command=sys.executable, args=[write_stub_server(tmp_path / "stub_mcp.py")]
    )


@pytest.fixture
def mcp_server(tmp_path):
    return make_config(tmp_path)


@pytest.mark.asyncio
async def test_mcp_client_discovers_tools(mcp_server):
    client = McpClient("stub", mcp_server.command, mcp_server.args)
    await client.start()
    try:
        assert client.initialized
        names = {t["name"] for t in client.tools}
        assert names == {"echo", "failing"}
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_mcp_client_call_tool_roundtrip(mcp_server):
    client = McpClient("stub", mcp_server.command, mcp_server.args)
    await client.start()
    try:
        result = await client.call_tool("echo", {"text": "hello-mcp"})
        text = result["content"][0]["text"]
        assert text == "hello-mcp"
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_mcp_manager_registers_server_prefixed_tools(mcp_server):
    manager = McpManager({"stub": mcp_server})
    await manager.start()
    try:
        assert manager.status["stub"] == "connected"
        wrappers = manager.build_wrappers()
        names = {w.name for w in wrappers}
        assert names == {"mcp_stub_echo", "mcp_stub_failing"}
        registry = ToolRegistry()
        for w in wrappers:
            registry.register(w)
        assert "mcp_stub_echo" in registry.list_tools()
        assert "mcp_stub_echo" in registry.list_tools_for_mode("build")
        assert "mcp_stub_echo" not in registry.list_tools_for_mode("plan", allowed_mcp={})
        assert "mcp_stub_echo" in registry.list_tools_for_mode(
            "build", allowed_mcp={"stub": ["echo"]}
        )
        assert "mcp_stub_echo" not in registry.list_tools_for_mode(
            "build", allowed_mcp={"stub": ["failing"]}
        )
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_mcp_wrapper_executes_via_manager(tmp_path):
    cfg = make_config(tmp_path)
    manager = McpManager({"stub": cfg})
    await manager.start()
    try:
        wrappers = {w.name: w for w in manager.build_wrappers()}
        result = await wrappers["mcp_stub_echo"].execute({"text": "wrap-ok"}, ".")
        assert result.success
        assert result.output == "wrap-ok"
        failed = await wrappers["mcp_stub_failing"].execute({}, ".")
        assert not failed.success
        assert "boom" in failed.error
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_mcp_manager_tolerates_failed_server(tmp_path):
    bad = McpServerConfig(command=os.sys.executable, args=["/nonexistent/missing_script.py"])
    manager = McpManager({"good": make_config(tmp_path), "bad": bad})
    await manager.start()
    try:
        assert manager.status["good"] == "connected"
        assert manager.status["bad"] == "failed"
        assert "bad" in manager.errors
        wrappers = {w.name for w in manager.build_wrappers()}
        assert "mcp_good_echo" in wrappers
        assert not any(n.startswith("mcp_bad_") for n in wrappers)
        servers = {s["name"]: s for s in manager.list_servers()}
        assert servers["bad"]["status"] == "failed"
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_registry_execute_runs_mcp_tool(tmp_path):
    cfg = make_config(tmp_path)
    manager = McpManager({"stub": cfg})
    await manager.start()
    try:
        registry = ToolRegistry()
        for w in manager.build_wrappers():
            registry.register(w)
        result = await registry.execute(
            "mcp_stub_echo", {"text": "via-registry"}, workspace_root=".", allowed_mcp=None
        )
        assert result.success
        assert result.output == "via-registry"
    finally:
        await manager.stop()


def test_mcp_servers_config_from_env(tmp_path, monkeypatch):
    stub_path = write_stub_server(tmp_path / "stub_mcp.py")
    payload = json.dumps({"stub": {"command": os.sys.executable, "args": [stub_path]}})
    monkeypatch.setenv("ZENITH_MCP_SERVERS", payload)
    monkeypatch.chdir(tmp_path)
    settings = load_config()
    assert "stub" in settings.mcp_servers
    assert settings.mcp_servers["stub"].command == os.sys.executable
    assert settings.mcp_servers["stub"].args == [stub_path]


def test_invalid_mcp_servers_json_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENITH_MCP_SERVERS", "{not-json")
    monkeypatch.chdir(tmp_path)
    settings = load_config()
    assert settings.mcp_servers == {}
