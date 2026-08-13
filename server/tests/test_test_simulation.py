import json
from pathlib import Path

import pytest

from server.config.constants import (
    COMPACTION_SIM_AFTER_TOKENS,
    COMPACTION_SIM_TOTAL_TOKENS,
    COMPACTION_SIM_USED_TOKENS,
)


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
async def test_simulation_context_compact_streams_full_sequence():
    handler = _make_handler()
    ws = _FakeWS()
    sid = handler._make_session({"title": "Compact Test"}).id

    returned = await handler._dispatch(ws, "context.compact", "compact_1", {}, sid)
    assert returned == sid

    events = [m for m in ws.sent if m.get("method") == "event"]
    response = [m for m in ws.sent if m.get("id") == "compact_1"]

    assert len(response) == 1
    assert response[0]["result"]["status"] == "compacted"

    kinds = [e["params"]["kind"] for e in events]
    assert kinds[0] == "context_compaction_started", kinds
    assert "context_compaction_phase" in kinds
    assert "context_compacted" in kinds
    assert kinds[-1] == "context_compaction_ended", kinds

    started = events[kinds.index("context_compaction_started")]
    started_data = started["params"]["data"]
    assert started_data["used"] == COMPACTION_SIM_USED_TOKENS
    assert started_data["total"] == COMPACTION_SIM_TOTAL_TOKENS

    ended = events[-1]
    ended_data = ended["params"]["data"]
    assert ended_data["used"] == COMPACTION_SIM_AFTER_TOKENS
    assert ended_data["total"] == COMPACTION_SIM_TOTAL_TOKENS
    assert ended_data.get("failed", False) is False
    assert isinstance(ended_data.get("summary"), str) and ended_data["summary"]
    # The model summary follows the opencode anchored-summary template.
    assert "## Objective" in ended_data["summary"]
    assert "## Work State" in ended_data["summary"]
    assert "## Next Move" in ended_data["summary"]
    assert "## Relevant Files" in ended_data["summary"]

    for evt in events:
        assert evt["params"]["session_id"] == sid


@pytest.mark.asyncio
async def test_simulation_context_compact_requires_active_session():
    handler = _make_handler()
    ws = _FakeWS()

    returned = await handler._dispatch(ws, "context.compact", "compact_2", {}, None)
    assert returned is None

    errors = [m for m in ws.sent if "error" in m]
    assert len(errors) == 1
    assert errors[0]["error"]["code"] == -32602
    assert "No active session" in errors[0]["error"]["message"]


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
