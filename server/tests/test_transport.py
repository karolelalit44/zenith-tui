from server.domain.events import Event, EventKind
from server.api.protocol import JsonRpcRequest, make_error_response, make_event, make_response


def test_jsonrpc_request():
    req = JsonRpcRequest(id="1", method="test", params={"key": "value"})
    assert req.jsonrpc == "2.0"
    assert req.method == "test"


def test_make_response():
    resp = make_response("1", {"ok": True})
    assert '"result"' in resp
    assert '"id":"1"' in resp


def test_make_error_response():
    resp = make_error_response("1", -32601, "Method not found")
    assert '"error"' in resp
    assert "Method not found" in resp


def test_make_event():
    event = Event(kind=EventKind.MESSAGE, data={"text": "hi"})
    msg = make_event(event)
    assert '"event"' in msg
    assert "thinking" not in msg


def test_make_event_with_all_kinds():
    for ek in EventKind:
        event = Event(kind=ek)
        msg = make_event(event)
        assert ek.value in msg
