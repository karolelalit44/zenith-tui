from server.domain.events import Event, EventKind


def test_event_serialization():
    event = Event(kind=EventKind.MESSAGE, data={"text": "test"})
    json_str = event.model_dump_json()
    parsed = Event.model_validate_json(json_str)
    assert parsed.kind == EventKind.MESSAGE
    assert parsed.data["text"] == "test"


def test_all_event_kinds():
    for ek in EventKind:
        event = Event(kind=ek)
        assert event.kind == ek


def test_event_with_session_id():
    event = Event(kind=EventKind.MESSAGE, data={"text": "hi"}, session_id="test-123")
    assert event.session_id == "test-123"


def test_event_has_id():
    event = Event(kind=EventKind.PROGRESS)
    assert event.id.startswith("evt_")


def test_event_timestamp():
    event = Event(kind=EventKind.PROGRESS)
    assert event.timestamp > 0


def test_make_event():
    from server.domain.events import make_event
    event = make_event(EventKind.ERROR, {"message": "oops"})
    assert event.kind == EventKind.ERROR
    assert event.data["message"] == "oops"
