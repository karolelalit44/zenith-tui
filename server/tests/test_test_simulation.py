import json
from pathlib import Path

import pytest


class _FakeWS:
    """Minimal websocket stand-in that records every message sent."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


def _make_handler():
    from server.api.test_websocket import TestSimulationHandler

    return TestSimulationHandler(workspace_root=str(Path.cwd()))


@pytest.mark.asyncio
async def test_simulation_context_compact_is_not_simulated():
    """The /ws/test demo backend no longer fakes compaction output.

    Real compaction (automatic + manual) runs through the production
    ``CompactionService`` (see test_compaction_service.py); the demo route must
    not present fabricated metrics as if they were real.
    """
    handler = _make_handler()
    ws = _FakeWS()
    sid = handler._make_session({"title": "Compact Test"}).id

    returned = await handler._dispatch(ws, "context.compact", "compact_1", {}, sid)
    assert returned == sid

    errors = [m for m in ws.sent if "error" in m]
    assert len(errors) == 1
    assert errors[0]["error"]["code"] == -32601
    assert "Method not found" in errors[0]["error"]["message"]


@pytest.mark.asyncio
async def test_simulation_memory_list_returns_static_payload():
    handler = _make_handler()
    ws = _FakeWS()

    returned = await handler._dispatch(ws, "memory.list", "memory_1", {}, None)
    assert returned is None

    responses = [m for m in ws.sent if m.get("id") == "memory_1"]
    assert len(responses) == 1
    result = responses[0]["result"]

    memories = result["memories"]
    assert isinstance(memories, list)
    assert result["total"] == len(memories) == 9
    assert len(memories) > 0

    scopes = {m["scope"] for m in memories}
    assert scopes == {"project", "session"}

    for m in memories:
        assert m["id"]
        assert m["scope"] in {"project", "session"}
        assert m["content"]
        assert isinstance(m.get("pinned", False), bool)

    assert any(m["pinned"] for m in memories)
    assert any(m["scope"] == "project" for m in memories)
    assert any(m["scope"] == "session" for m in memories)


@pytest.mark.asyncio
async def test_simulation_memory_list_ignores_params():
    handler = _make_handler()
    ws = _FakeWS()

    returned = await handler._dispatch(
        ws, "memory.list", "memory_2", {"scope": "session", "limit": 1}, None
    )
    assert returned is None

    responses = [m for m in ws.sent if m.get("id") == "memory_2"]
    assert len(responses) == 1
    # Static backend: params are accepted for forward-compat but do not filter.
    assert len(responses[0]["result"]["memories"]) == 9


def test_todo_and_hrms_simulations_match_prompts_in_build_mode():
    handler = _make_handler()
    sims = handler._load_simulations()

    files = [s["_file"] for s in sims]
    assert "todo-lifecycle.json" in files, files
    assert "hrms-build.json" in files, files
    assert "full-showcase.json" in files, files

    assert (
        handler._match(sims, "simulate todo lifecycle", "build")["_file"] == "todo-lifecycle.json"
    )
    assert handler._match(sims, "build the hrms django app", "build")["_file"] == "hrms-build.json"
    # Single prompt that drives BOTH simulations in one response.
    assert handler._match(sims, "run the full showcase", "build")["_file"] == "full-showcase.json"

    # All three simulations are build-mode only: in plan mode they fall back to
    # the default response rather than hijacking the prompt.
    assert handler._match(sims, "simulate todo lifecycle", "plan")["_file"] == "_default.json"
    assert handler._match(sims, "build the hrms django app", "plan")["_file"] == "_default.json"
    assert handler._match(sims, "run the full showcase", "plan")["_file"] == "_default.json"


def test_new_simulation_event_kinds_are_all_known():
    from server.domain.events import EventKind

    handler = _make_handler()
    sims = handler._load_simulations()
    targets = {"todo-lifecycle.json", "hrms-build.json", "full-showcase.json"}

    seen = 0
    for sim in sims:
        if sim["_file"] not in targets:
            continue
        seen += 1
        events = [evt for entry in sim.get("responses") or [] for evt in entry.get("events") or []]
        assert events, sim["_file"]
        for evt in events:
            kind = evt.get("kind")
            assert kind, f"{sim['_file']}: event missing kind"
            # Unknown kinds silently degrade to MESSAGE in playback, so any kind
            # used here must be a real EventKind value.
            EventKind(kind)
    assert seen == 3


@pytest.mark.asyncio
async def test_todo_lifecycle_playback_streams_board_and_report(monkeypatch):
    handler = _make_handler()
    ws = _FakeWS()
    sid = handler._make_session({"title": "Todo Playback"}).id

    async def _noop(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("server.api.test_websocket.asyncio.sleep", _noop)

    returned = await handler._dispatch(
        ws, "prompt.send", "todo_1", {"content": "simulate todo lifecycle"}, sid
    )
    assert returned == sid
    await handler._active_tasks[sid]

    events = [m for m in ws.sent if m.get("method") == "event"]
    kinds = [e["params"]["kind"] for e in events]
    assert kinds.count("todo_board") == 9, kinds
    assert kinds.count("todo_test") == 8, kinds
    assert kinds[-1] == "success", kinds
    for evt in events:
        assert evt["params"]["session_id"] == sid

    # The consolidated report card survives the wire intact.
    last_test = [e for e in events if e["params"]["kind"] == "todo_test"][-1]
    data = last_test["params"]["data"]
    assert data["phase"] == "persist"
    assert data["passed"] is True
    assert len(data["assertions"]) > 0


@pytest.mark.asyncio
async def test_hrms_playback_streams_orchestration_and_compaction(monkeypatch):
    handler = _make_handler()
    ws = _FakeWS()
    sid = handler._make_session({"title": "HRMS Playback"}).id

    async def _noop(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("server.api.test_websocket.asyncio.sleep", _noop)

    returned = await handler._dispatch(
        ws, "prompt.send", "hrms_1", {"content": "build the hrms django app"}, sid
    )
    assert returned == sid
    await handler._active_tasks[sid]

    events = [m for m in ws.sent if m.get("method") == "event"]
    kinds = [e["params"]["kind"] for e in events]
    assert kinds.count("agent_orchestration") == 7, kinds
    assert kinds.count("todo_board") == 17, kinds
    assert kinds.count("progress") == 3, kinds
    assert kinds.count("context_compaction_started") == 1, kinds
    assert kinds.count("context_compaction_ended") == 1, kinds
    assert kinds.count("error") == 1, kinds
    assert "tool_call" in kinds and "tool_result" in kinds
    assert kinds[-1] == "success", kinds
    for evt in events:
        assert evt["params"]["session_id"] == sid

    # Final board reflects every todo_board snapshot that crossed the wire.
    boards = [e["params"]["data"]["board"] for e in events if e["params"]["kind"] == "todo_board"]
    assert len(boards[-1]) == 7
    assert {i["id"] for i in boards[-1]} == {"H1", "H2", "H3", "H4", "H5", "H6", "H7"}


@pytest.mark.asyncio
async def test_full_showcase_playback_combines_lifecycle_then_hrms(monkeypatch):
    handler = _make_handler()
    ws = _FakeWS()
    sid = handler._make_session({"title": "Showcase Playback"}).id

    async def _noop(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("server.api.test_websocket.asyncio.sleep", _noop)

    returned = await handler._dispatch(
        ws, "prompt.send", "showcase_1", {"content": "run the full showcase"}, sid
    )
    assert returned == sid
    await handler._active_tasks[sid]

    events = [m for m in ws.sent if m.get("method") == "event"]
    kinds = [e["params"]["kind"] for e in events]
    assert kinds[0] == "thinking", kinds
    assert kinds.count("todo_test") == 8, kinds
    assert kinds.count("todo_board") == 26, kinds
    assert kinds.count("agent_orchestration") == 12, kinds
    assert kinds.count("context_compaction_started") == 1, kinds
    assert kinds.count("error") == 1, kinds
    # Two success cards in the stream plus the trailing success the server
    # appends after a full playback.
    assert kinds.count("success") == 3, kinds
    assert kinds[-1] == "success", kinds
    for evt in events:
        assert evt["params"]["session_id"] == sid

    # Lifecycle verification runs first, then the HRMS build: the whole
    # todo_test report must land before any HRMS-only compaction phase.
    first_test = kinds.index("todo_test")
    compaction = kinds.index("context_compaction_started")
    assert first_test < compaction, kinds

    # Both halves keep their terminal state intact.
    last_test = [e for e in events if e["params"]["kind"] == "todo_test"][-1]
    assert last_test["params"]["data"]["phase"] == "persist"
    boards = [e["params"]["data"]["board"] for e in events if e["params"]["kind"] == "todo_board"]
    assert {i["id"] for i in boards[-1]} == {"H1", "H2", "H3", "H4", "H5", "H6", "H7"}
