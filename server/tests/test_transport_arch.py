import pytest

from server.api.protocol import (
    Connection,
    JsonRpcRequest,
    JsonRpcResponse,
    TransportService,
    make_error_response,
    make_response,
    serialize_event,
)
from server.api.websocket import ConnectionManager
from server.config.settings import AppSettings
from server.domain.events import Event, EventKind


class TestWebSocketOriginPolicy:
    def test_allows_exact_configured_origin(self):
        from server.api.server import _is_allowed_ws_origin

        config = AppSettings(
            allowed_ws_origins=["https://app.example.com", "http://localhost:8765"],
            allow_empty_ws_origin=False,
        )
        assert _is_allowed_ws_origin(config, "https://app.example.com") is True
        assert _is_allowed_ws_origin(config, "http://localhost:8765") is True

    def test_rejects_substring_origin_spoof(self):
        from server.api.server import _is_allowed_ws_origin

        config = AppSettings(allowed_ws_origins=["http://localhost"], allow_empty_ws_origin=False)
        assert _is_allowed_ws_origin(config, "https://localhost.evil.example") is False

    def test_empty_origin_is_explicit_policy(self):
        from server.api.server import _is_allowed_ws_origin

        assert _is_allowed_ws_origin(AppSettings(allow_empty_ws_origin=True), "") is True
        assert _is_allowed_ws_origin(AppSettings(allow_empty_ws_origin=False), "") is False


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

    def test_serialize_event(self):
        event = Event(kind=EventKind.MESSAGE, data={"text": "hi"})
        s = serialize_event(event)
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
