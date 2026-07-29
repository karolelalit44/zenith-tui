"""Tests for transport architecture — protocol, ConnectionManager, TransportService."""

import pytest

from core.events import Event, EventKind
from transport.protocol import (
    Connection,
    JsonRpcMethod,
    JsonRpcRequest,
    JsonRpcResponse,
    TransportService,
    make_error_response,
    make_event,
    make_response,
)
from transport.websocket import ConnectionManager

# ── JsonRpcMethod ────────────────────────────────────────────────────────

class TestJsonRpcMethod:
    def test_all_methods_exist(self):
        methods = [
            "session.create", "session.list", "session.resume", "session.export",
            "prompt.send", "prompt.cancel",
            "provider.validate", "provider.models", "provider.list",
            "tools.list",
            "workspace.status", "workspace.diff", "workspace.log", "workspace.repo_map",
            "permission.response",
            "health",
        ]
        for m in methods:
            assert JsonRpcMethod(m) is not None

    def test_method_values_are_strings(self):
        for m in JsonRpcMethod:
            assert isinstance(m.value, str)
            assert len(m.value) > 0


# ── JsonRpcRequest ───────────────────────────────────────────────────────

class TestJsonRpcRequest:
    def test_create_request(self):
        req = JsonRpcRequest(id="1", method="test", params={"key": "value"})
        assert req.jsonrpc == "2.0"
        assert req.method == "test"
        assert req.params["key"] == "value"

    def test_request_default_params(self):
        req = JsonRpcRequest(id="1", method="test")
        assert req.params == {}


# ── JsonRpcResponse ──────────────────────────────────────────────────────

class TestJsonRpcResponse:
    def test_success_response(self):
        resp = JsonRpcResponse(id="1", result={"ok": True})
        assert resp.result["ok"] is True
        assert resp.error is None

    def test_error_response(self):
        resp = JsonRpcResponse(id="1", error={"code": -32601, "message": "not found"})
        assert resp.error["code"] == -32601


# ── Serialization helpers ────────────────────────────────────────────────

class TestSerialization:
    def test_make_response(self):
        s = make_response("1", {"ok": True})
        assert '"result"' in s
        assert '"id":"1"' in s

    def test_make_error_response(self):
        s = make_error_response("1", -32601, "Method not found")
        assert '"error"' in s
        assert "Method not found" in s

    def test_make_event(self):
        event = Event(kind=EventKind.MESSAGE, data={"text": "hi"})
        s = make_event(event)
        assert '"event"' in s
        assert "message" in s


# ── Connection model ─────────────────────────────────────────────────────

class TestConnection:
    def test_connection(self):
        c = Connection(session_id="sess_1", client="127.0.0.1:1234")
        assert c.session_id == "sess_1"
        assert c.client == "127.0.0.1:1234"


# ── TransportService ABC ────────────────────────────────────────────────

class TestTransportServiceABC:
    def test_abc_cannot_instantiate(self):
        with pytest.raises(TypeError):
            TransportService()


# ── ConnectionManager ────────────────────────────────────────────────────

class TestConnectionManager:
    def test_implements_transport_service(self):
        cm = ConnectionManager()
        assert isinstance(cm, TransportService)

    def test_get_connections_empty(self):
        cm = ConnectionManager()
        assert cm.get_connections() == []

    @pytest.mark.asyncio
    async def test_stop_disconnects_all(self):
        cm = ConnectionManager()
        # No connections to disconnect
        await cm.stop()
        assert cm.get_connections() == []
