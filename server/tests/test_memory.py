"""Tests for HP-7: durable memory store (memory/*.md loaded into context)."""

from __future__ import annotations

import pytest

from server.agents.context import ContextManager
from server.config.settings import AppSettings
from server.domain.message import Message
from server.providers.base import BaseProvider
from server.sessions.memory import MemoryStore
from server.sessions.history import HistoryManager


class TestMemoryStore:
    def test_append_creates_file(self, temp_dir):
        store = MemoryStore(temp_dir)
        path = store.append("sess-1", "The user prefers Python over Go.")
        assert path.exists()
        assert path.parent.name == "memory"
        assert path.name == "sess-1.md"
        assert "Python over Go" in path.read_text(encoding="utf-8")

    def test_append_accumulates(self, temp_dir):
        store = MemoryStore(temp_dir)
        store.append("s-1", "fact one")
        store.append("s-1", "fact two")
        text = (store.dir / "s-1.md").read_text(encoding="utf-8")
        assert "fact one" in text
        assert "fact two" in text

    def test_load_across_sessions_same_workspace(self, temp_dir):
        store = MemoryStore(temp_dir)
        store.append("old-session", "Use type hints everywhere")
        loaded = MemoryStore(temp_dir).load()
        assert "Use type hints everywhere" in loaded
        assert "old-session" in loaded

    def test_rollover_caps_file_size(self, temp_dir):
        store = MemoryStore(temp_dir, max_chars=200)
        store.append("s-1", "x" * 500)
        store.append("s-1", "y" * 500)
        assert len((store.dir / "s-1.md").read_text(encoding="utf-8")) <= 260

    def test_empty_facts_does_not_write(self, temp_dir):
        store = MemoryStore(temp_dir)
        store.append("s-1", "   ")
        assert not (store.dir / "s-1.md").exists()
        assert store.load() == ""


class TestSummarizePersistsMemory:
    class SummaryProvider(BaseProvider):
        def __init__(self):
            super().__init__("test", "test-model")

        async def complete(self, messages, tools=None) -> str:
            return "KEY DECISION: the auth token must be rotated daily."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["test-model"]

    @pytest.mark.asyncio
    async def test_force_summarize_writes_memory_file(self, temp_dir):
        config = AppSettings(
            db_path=str(temp_dir / "test.db"),
            workspace_root=str(temp_dir),
        )
        msgs = [Message(session_id="s1", role="user", content="build auth"),
                Message(session_id="s1", role="assistant", content="done")]
        hm = HistoryManager(config, self.SummaryProvider())
        summary = await hm.summarize(msgs, "test-model", session_id="s1")

        assert "auth token" in summary
        memory_file = temp_dir / "memory" / "s1.md"
        assert memory_file.exists()
        assert "auth token" in memory_file.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_no_context_fallback_not_persisted(self, temp_dir):
        class EmptyProvider(BaseProvider):
            def __init__(self):
                super().__init__("test", "test-model")

            async def complete(self, messages, tools=None) -> str:
                raise RuntimeError("down")

            async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
                return
                yield

            async def validate(self) -> bool:
                return True

            async def list_models(self) -> list[str]:
                return ["test-model"]

        config = AppSettings(
            db_path=str(temp_dir / "test.db"),
            workspace_root=str(temp_dir),
        )
        hm = HistoryManager(config, EmptyProvider())
        await hm.summarize([], "test-model", session_id="s1")
        assert not (temp_dir / "memory" / "s1.md").exists()


class TestMemoryInContext:
    def test_build_messages_injects_memory(self, temp_dir):
        MemoryStore(temp_dir).append("prev", "The stack is FastAPI + Ink.")
        config = AppSettings(
            max_context_tokens=128000,
            repo_map_enabled=False,
            db_path=str(temp_dir / "test.db"),
            workspace_root=str(temp_dir),
        )
        cm = ContextManager(config)
        messages = cm.build_messages([], "SYS", "hi", "test-model", repo_map="")
        assert any(m["role"] == "system" and "<memory>" in m["content"] for m in messages)
        memory_msg = next(m for m in messages if "<memory>" in m["content"])
        assert "FastAPI + Ink" in memory_msg["content"]

    def test_memory_disabled(self, temp_dir):
        MemoryStore(temp_dir).append("prev", "should not load")
        config = AppSettings(
            max_context_tokens=128000,
            repo_map_enabled=False,
            memory_enabled=False,
            db_path=str(temp_dir / "test.db"),
            workspace_root=str(temp_dir),
        )
        cm = ContextManager(config)
        messages = cm.build_messages([], "SYS", "hi", "test-model", repo_map="")
        assert all("<memory>" not in m["content"] for m in messages)
        assert cm.get_memory() == ""

    def test_memory_merged_when_no_system_role(self, temp_dir):
        MemoryStore(temp_dir).append("prev", "remember this fact")
        config = AppSettings(
            max_context_tokens=128000,
            repo_map_enabled=False,
            db_path=str(temp_dir / "test.db"),
            workspace_root=str(temp_dir),
        )
        cm = ContextManager(config)
        messages = cm.build_messages(
            [], "SYS", "hi", "test-model", use_system_prompt=False, repo_map="",
        )
        assert all(m["role"] != "system" for m in messages)
        assert "<memory>" in messages[0]["content"]

    def test_new_session_same_workspace_loads_memory(self, temp_dir):
        MemoryStore(temp_dir).append("session-A", "DRY principle enforced")
        cm = ContextManager(AppSettings(
            max_context_tokens=128000,
            repo_map_enabled=False,
            db_path=str(temp_dir / "test.db"),
            workspace_root=str(temp_dir),
        ))
        memory_text = cm.get_memory()
        assert "DRY principle enforced" in memory_text
