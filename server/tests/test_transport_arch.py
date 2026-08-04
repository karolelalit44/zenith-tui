import pytest

from server.api.protocol import (
    Connection,
    JsonRpcRequest,
    JsonRpcResponse,
    TransportService,
    make_error_response,
    make_event,
    make_response,
)
from server.api.websocket import ConnectionManager
from server.domain.events import Event, EventKind


class TestJsonRpcRequest:
    def test_create_request(self):
        req = JsonRpcRequest(id="1", method="test", params={"key": "value"})
        assert req.jsonrpc == "2.0"
        assert req.method == "test"
        assert req.params["key"] == "value"

    def test_request_default_params(self):
        req = JsonRpcRequest(id="1", method="test")
        assert req.params == {}


class TestJsonRpcResponse:
    def test_success_response(self):
        resp = JsonRpcResponse(id="1", result={"ok": True})
        assert resp.result["ok"] is True
        assert resp.error is None

    def test_error_response(self):
        resp = JsonRpcResponse(id="1", error={"code": -32601, "message": "not found"})
        assert resp.error["code"] == -32601


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


class TestConnection:
    def test_connection(self):
        c = Connection(session_id="sess_1", client="127.0.0.1:1234")
        assert c.session_id == "sess_1"
        assert c.client == "127.0.0.1:1234"


class TestTransportServiceABC:
    def test_abc_cannot_instantiate(self):
        with pytest.raises(TypeError):
            TransportService()


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
        await cm.stop()
        assert cm.get_connections() == []
