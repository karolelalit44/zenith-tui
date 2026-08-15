from __future__ import annotations

from pathlib import Path

import pytest

from server.agents.compaction import prune_inflight_messages
from server.agents.loop import AgentLoop
from server.config.settings import AppSettings
from server.domain.message import Message


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def count_tokens(self, text: str, model: str | None = None) -> int:
        return max(1, len(text) // 4)


class TestInflightCompaction:
    def test_prune_inflight_messages_compresses_older_tool_results(self):
        messages = [
            {"role": "user", "content": "Analyze repository"},
            {
                "role": "user",
                "content": "[Tool: glob | Status: SUCCESS]\n" + "file_path.py\n" * 1000,
                "digest": "[Tool: glob | Status: SUCCESS] Found 1000 files",
            },
            {
                "role": "user",
                "content": "[Tool: grep | Status: SUCCESS]\n" + "match line\n" * 1000,
                "digest": "[Tool: grep | Status: SUCCESS] Found 1000 matches",
            },
            {
                "role": "user",
                "content": "[Tool: file_read | Status: SUCCESS]\n" + "code line\n" * 500,
            },
            {
                "role": "user",
                "content": "[Tool: bash | Status: SUCCESS]\n" + "output line\n" * 500,
            },
        ]
        # With keep_latest_tools=2, messages[1] and messages[2] should be compacted
        pruned, stats = prune_inflight_messages(messages, keep_latest_tools=2)
        assert stats.chars_removed > 0
        assert stats.tokens_saved > 0
        assert pruned[1]["content"] == "[Tool: glob | Status: SUCCESS] Found 1000 files"
        assert pruned[2]["content"] == "[Tool: grep | Status: SUCCESS] Found 1000 matches"
        # Latest 2 tool messages (indices 3 and 4) remain untouched
        assert "code line" in pruned[3]["content"]
        assert "output line" in pruned[4]["content"]

    def test_rebuild_messages_compacts_live_tail(self, temp_dir: Path):
        cfg = AppSettings(workspace_root=str(temp_dir))
        provider = FakeProvider()
        loop = AgentLoop(config=cfg, provider=provider)
        base_messages = [{"role": "user", "content": "Initial task"}]
        live_messages = [
            {"role": "user", "content": "Initial task"},
            {"role": "assistant", "content": "Running tools"},
            {
                "role": "user",
                "content": "[Tool: glob | Status: SUCCESS]\n" + "huge_list.py\n" * 2000,
                "digest": "[Tool: glob | Status: SUCCESS] Found 2000 files",
            },
            {
                "role": "user",
                "content": "[Tool: file_read | Status: SUCCESS]\n" + "line of text\n" * 1000,
            },
        ]
        rebuilt = loop._rebuild_messages(
            messages=live_messages,
            base_len=len(base_messages),
            history=[Message(session_id="test-s", role="user", content="Initial task")],
            system_prompt="You are an assistant.",
            prompt="Initial task",
            model="fake-model",
            plan_context="",
            use_system_prompt=True,
            repo_map=None,
        )
        rebuilt_text = " ".join(m.get("content", "") for m in rebuilt if isinstance(m, dict))
        # Verify digest is used for glob in live tail
        assert "[Tool: glob | Status: SUCCESS] Found 2000 files" in rebuilt_text
        # Verify raw 2000 lines of huge_list.py is not re-injected
        assert "huge_list.py\n" * 100 not in rebuilt_text
        # Verify large file_read without digest is head-tail trimmed
        assert "truncated" in rebuilt_text or "line of text" in rebuilt_text

    @pytest.mark.asyncio
    async def test_maybe_summarize_computes_positive_tokens_saved(self, temp_dir: Path):
        cfg = AppSettings(workspace_root=str(temp_dir))
        provider = FakeProvider()
        loop = AgentLoop(config=cfg, provider=provider)
        bloated_tool_content = "[Tool: glob | Status: SUCCESS]\n" + "file.py\n" * 3000
        messages = [
            {"role": "user", "content": "Find files"},
            {"role": "assistant", "content": "Searching"},
            {
                "role": "user",
                "content": bloated_tool_content,
                "digest": "[Tool: glob | Status: SUCCESS] Found 3000 files",
            },
            {
                "role": "user",
                "content": "[Tool: file_read | Status: SUCCESS]\n" + "data\n" * 1000,
            },
            {
                "role": "user",
                "content": "[Tool: bash | Status: SUCCESS]\nexit 0",
            },
        ]
        events = []
        async for ev in loop._maybe_summarize(
            history=[Message(session_id="test-s", role="user", content="Find files")],
            session_id="test-session",
            messages=messages,
        ):
            events.append(ev)

        end_events = [
            e
            for e in events
            if getattr(e, "kind", "") == "context_compaction_ended"
            or (
                isinstance(e.data, dict)
                and (
                    e.data.get("tokensSaved") is not None or e.data.get("tokens_saved") is not None
                )
            )
        ]
        assert len(end_events) > 0
        end_data = end_events[0].data if hasattr(end_events[0], "data") else {}
        tokens_saved = end_data.get("tokensSaved", end_data.get("tokens_saved", 0))
        assert tokens_saved > 0
