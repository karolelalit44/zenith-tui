"""Tests for MCP integration — McpClient, McpManager, dynamic tool registration, config loading."""

from __future__ import annotations

import json
import os
import textwrap

import pytest

from server.config.loader import load_config
from server.config.settings import McpServerConfig
from server.mcp.client import McpClient
from server.mcp.manager import McpManager
from server.toolkit.registry import ToolRegistry

STUB_SERVER = r"""
import json
import sys

def read_message():
    header = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line.strip() == b"":
            break
        k, _, v = line.decode().partition(":")
        header[k.strip().lower()] = v.strip()
    length = int(header.get("content-length", 0))
    if length == 0:
        return None
    return json.loads(sys.stdin.buffer.read(length))

def write_message(msg):
    body = json.dumps(msg).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
    sys.stdout.buffer.flush()

while True:
    msg = read_message()
    if msg is None:
        break
    method = msg.get("method")
    if method == "initialize":
        write_message({"jsonrpc": "2.0", "id": msg["id"], "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "stub", "version": "1.0.0"},
        }})
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        write_message({"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": [
            {"name": "echo", "description": "Echoes input",
             "inputSchema": {"type": "object",
                             "properties": {"text": {"type": "string"}},
                             "required": ["text"]}},
            {"name": "failing", "description": "Always errors",
             "inputSchema": {"type": "object", "properties": {}}},
        ]}})
    elif method == "tools/call":
        name = msg["params"]["name"]
        args = msg["params"]["arguments"]
        if name == "failing":
            write_message({"jsonrpc": "2.0", "id": msg["id"], "result": {
                "content": [{"type": "text", "text": "boom"}], "isError": True,
            }})
        else:
            write_message({"jsonrpc": "2.0", "id": msg["id"], "result": {
                "content": [{"type": "text", "text": args.get("text", "")}], "isError": False,
            }})
    else:
        write_message({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "not found"}})
"""


def write_stub_server(path):
    path.write_text(textwrap.dedent(STUB_SERVER))
    return str(path)


def make_config(tmp_path) -> McpServerConfig:
    return McpServerConfig(
        command=os.sys.executable, args=[write_stub_server(tmp_path / "stub_mcp.py")]
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
        # Build mode (allowed_mcp=None) exposes all MCP tools
        assert "mcp_stub_echo" in registry.list_tools_for_mode("build")
        # Plan mode ({}) hides them
        assert "mcp_stub_echo" not in registry.list_tools_for_mode("plan", allowed_mcp={})
        # Explicit allowlist matches server-prefixed names
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
            "mcp_stub_echo",
            {"text": "via-registry"},
            workspace_root=".",
            allowed_mcp=None,
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
