from __future__ import annotations

from pathlib import Path

import pytest

from server.agents.loop import AgentLoop
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.domain.message import Message


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def count_tokens(self, text: str, model: str | None = None) -> int:
        return max(1, len(text) // 4)


class TestCompactionUIEvents:
    @pytest.mark.asyncio
    async def test_compaction_emits_ordered_phases_and_no_raw_warnings(self, temp_dir: Path):
        cfg = AppSettings(workspace_root=str(temp_dir))
        provider = FakeProvider()
        loop = AgentLoop(config=cfg, provider=provider)
        messages = [
            {"role": "user", "content": "Find items"},
            {
                "role": "user",
                "content": "[Tool: glob | Status: SUCCESS]\n" + "f.py\n" * 2000,
                "digest": "[Tool: glob | Status: SUCCESS] Found 2000 files",
            },
        ]
        events = []
        async for ev in loop._maybe_summarize(
            history=[Message(session_id="s1", role="user", content="Find items")],
            session_id="s1",
            messages=messages,
        ):
            events.append(ev)

        event_kinds = [ev.kind for ev in events]

        # Verify started event
        assert EventKind.CONTEXT_COMPACTION_STARTED in event_kinds

        # Verify all 3 phase events in order
        phase_events = [ev for ev in events if ev.kind == EventKind.CONTEXT_COMPACTION_PHASE]
        phases = [ev.data.get("phase") for ev in phase_events]
        assert phases == ["preserving", "compacting", "verifying"]

        # Verify ended event
        assert EventKind.CONTEXT_COMPACTION_ENDED in event_kinds

        # Verify ZERO raw warning events emitted
        warning_events = [ev for ev in events if ev.kind == EventKind.WARNING]
        assert len(warning_events) == 0, f"Expected 0 raw warning events, got: {warning_events}"
