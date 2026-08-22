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
    @staticmethod
    def _noop_messages():
        return [
            {"role": "user", "content": "Find items"},
            {
                "role": "user",
                "content": "[Tool: glob | Status: SUCCESS]\n" + "f.py\n" * 2000,
                "digest": "[Tool: glob | Status: SUCCESS] Found 2000 files",
            },
        ]

    @pytest.mark.asyncio
    async def test_compaction_emits_ordered_phases_and_no_raw_warnings(self, temp_dir: Path):
        cfg = AppSettings(workspace_root=str(temp_dir))
        provider = FakeProvider()
        loop = AgentLoop(config=cfg, provider=provider)
        messages = self._noop_messages()
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

        # Nothing is summarizable here (single-turn history, single tool result
        # that intraturn pruning keeps intact): the attempt must end as an
        # explicit skip after the preparation phases -- never a fabricated
        # success, never a verifying phase over an untouched context.
        phase_events = [ev for ev in events if ev.kind == EventKind.CONTEXT_COMPACTION_PHASE]
        phases = [ev.data.get("phase") for ev in phase_events]
        assert phases == ["preserving", "compacting"]

        ended = next(ev for ev in events if ev.kind == EventKind.CONTEXT_COMPACTION_ENDED)
        assert ended.data.get("status") == "skipped"
        # The live context was left untouched.
        assert messages[1]["content"].startswith("[Tool: glob | Status: SUCCESS]\n")

        # Verify ZERO raw warning events emitted
        warning_events = [ev for ev in events if ev.kind == EventKind.WARNING]
        assert len(warning_events) == 0, f"Expected 0 raw warning events, got: {warning_events}"

    @pytest.mark.asyncio
    async def test_compaction_full_pipeline_phases_on_real_compaction(self, temp_dir: Path):
        """A compaction with real work walks preserving -> compacting -> verifying."""
        cfg = AppSettings(workspace_root=str(temp_dir), max_context_tokens=4000)
        provider = FakeProvider()
        loop = AgentLoop(config=cfg, provider=provider)
        history = [
            Message(session_id="s1", role="user", content=f"turn {i} " + "x" * 2200)
            for i in range(6)
        ]
        messages = [
            {"role": "user", "content": "Find items"},
            {
                "role": "user",
                "content": "[Tool: glob | Status: SUCCESS]\n" + "f.py\n" * 2000,
                "digest": "[Tool: glob | Status: SUCCESS] Found 2000 files",
            },
        ]
        events = []
        async for ev in loop._maybe_summarize(history=history, session_id="s1", messages=messages):
            events.append(ev)

        phase_events = [ev for ev in events if ev.kind == EventKind.CONTEXT_COMPACTION_PHASE]
        phases = [ev.data.get("phase") for ev in phase_events]
        assert phases == ["preserving", "compacting", "verifying"]

        ended = next(ev for ev in events if ev.kind == EventKind.CONTEXT_COMPACTION_ENDED)
        assert ended.data.get("status") == "completed"

        warning_events = [ev for ev in events if ev.kind == EventKind.WARNING]
        assert len(warning_events) == 0, f"Expected 0 raw warning events, got: {warning_events}"

    @pytest.mark.asyncio
    async def test_compaction_events_carry_per_tier_tokens(self, temp_dir: Path):
        # Per-tier payloads are only complete on a real compaction (the
        # verifying phase carries tokensAfter); use a small window so the
        # attempt performs actual work instead of ending as a skip.
        cfg = AppSettings(workspace_root=str(temp_dir), max_context_tokens=4000)
        provider = FakeProvider()
        loop = AgentLoop(config=cfg, provider=provider)
        history = [
            Message(session_id="s1", role="user", content=f"turn {i} " + "x" * 2200)
            for i in range(6)
        ]
        messages = [
            {"role": "user", "content": "Find items"},
            {
                "role": "user",
                "content": "[Tool: glob | Status: SUCCESS]\n" + "f.py\n" * 2000,
                "digest": "[Tool: glob | Status: SUCCESS] Found 2000 files",
            },
        ]
        events = []
        async for ev in loop._maybe_summarize(history=history, session_id="s1", messages=messages):
            events.append(ev)

        tiers = {"system", "state", "summary", "handoff", "window", "user", "tools"}

        started = next(ev for ev in events if ev.kind == EventKind.CONTEXT_COMPACTION_STARTED)
        assert set(started.data["tokens"].keys()) == tiers
        assert started.data["tokens"]["tools"] > 0

        verifying = next(
            ev
            for ev in events
            if ev.kind == EventKind.CONTEXT_COMPACTION_PHASE and ev.data.get("phase") == "verifying"
        )
        assert set(verifying.data["tokensBefore"].keys()) == tiers
        assert set(verifying.data["tokensAfter"].keys()) == tiers

        ended = next(ev for ev in events if ev.kind == EventKind.CONTEXT_COMPACTION_ENDED)
        assert set(ended.data["tokensBefore"].keys()) == tiers
        assert set(ended.data["tokensAfter"].keys()) == tiers
        assert ended.data["tokensSaved"] > 0
        assert "failed" not in ended.data
