from __future__ import annotations

from server.agents.context import ContextManager
from server.config.constants import DEFAULT_CONTEXT_WINDOW
from server.config.settings import AppSettings
from server.domain.message import Message
from server.sessions.memory import MemoryStore


def _resumed_history():
    return [Message(session_id="s1", role="user", content="Earlier prompt")]


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

    def test_rollover_drops_oldest_blocks_whole(self, temp_dir):
        store = MemoryStore(temp_dir, max_chars=300)
        store.append("s-1", "FIRST fact " + "a" * 80)
        store.append("s-1", "SECOND fact " + "b" * 80)
        store.append("s-1", "THIRD fact " + "c" * 80)
        text = (store.dir / "s-1.md").read_text(encoding="utf-8")
        assert len(text) <= 340
        assert "THIRD" in text
        assert "SECOND" in text
        assert "FIRST" not in text

    def test_empty_facts_does_not_write(self, temp_dir):
        store = MemoryStore(temp_dir)
        store.append("s-1", "   ")
        assert not (store.dir / "s-1.md").exists()
        assert store.load() == ""


class TestMemoryInContext:
    def test_build_messages_injects_memory(self, temp_dir):
        MemoryStore(temp_dir).append("prev", "The stack is FastAPI + Ink.")
        config = AppSettings(
            max_context_tokens=DEFAULT_CONTEXT_WINDOW,
            repo_map_enabled=False,
            home_dir=str(temp_dir / "test.db"),
            workspace_root=str(temp_dir),
        )
        cm = ContextManager(config)
        messages = cm.build_messages(_resumed_history(), "SYS", "hi", "test-model", repo_map="")
        assert any(m["role"] == "system" and "<memory>" in m["content"] for m in messages)
        memory_msg = next(m for m in messages if "<memory>" in m["content"])
        assert "FastAPI + Ink" in memory_msg["content"]

    def test_memory_not_injected_on_fresh_session(self, temp_dir):
        MemoryStore(temp_dir).append("prev", "The stack is FastAPI + Ink.")
        config = AppSettings(
            max_context_tokens=DEFAULT_CONTEXT_WINDOW,
            repo_map_enabled=False,
            home_dir=str(temp_dir / "test.db"),
            workspace_root=str(temp_dir),
        )
        cm = ContextManager(config)
        messages = cm.build_messages([], "SYS", "hi", "test-model", repo_map="")
        assert all("<memory>" not in m["content"] for m in messages)
        assert len(messages) == 2
        assert messages[-1]["content"] == "hi"

    def test_memory_disabled(self, temp_dir):
        MemoryStore(temp_dir).append("prev", "should not load")
        config = AppSettings(
            max_context_tokens=DEFAULT_CONTEXT_WINDOW,
            repo_map_enabled=False,
            memory_enabled=False,
            home_dir=str(temp_dir / "test.db"),
            workspace_root=str(temp_dir),
        )
        cm = ContextManager(config)
        messages = cm.build_messages(_resumed_history(), "SYS", "hi", "test-model", repo_map="")
        assert all("<memory>" not in m["content"] for m in messages)
        assert cm.get_memory() == ""

    def test_memory_skipped_when_budget_tight(self, temp_dir):
        MemoryStore(temp_dir).append("prev", "x " * 8000)
        config = AppSettings(
            max_context_tokens=8000,
            repo_map_enabled=False,
            home_dir=str(temp_dir / "test.db"),
            workspace_root=str(temp_dir),
        )
        cm = ContextManager(config)
        messages = cm.build_messages(_resumed_history(), "SYS", "hi", "test-model", repo_map="")
        assert all("<memory>" not in m["content"] for m in messages)
        assert messages[-1]["content"] == "hi"

    def test_memory_merged_when_no_system_role(self, temp_dir):
        MemoryStore(temp_dir).append("prev", "remember this fact")
        config = AppSettings(
            max_context_tokens=DEFAULT_CONTEXT_WINDOW,
            repo_map_enabled=False,
            home_dir=str(temp_dir / "test.db"),
            workspace_root=str(temp_dir),
        )
        cm = ContextManager(config)
        messages = cm.build_messages(
            _resumed_history(),
            "SYS",
            "hi",
            "test-model",
            use_system_prompt=False,
            repo_map="",
        )
        assert all(m["role"] != "system" for m in messages)
        assert "<memory>" in messages[0]["content"]

    def test_new_session_same_workspace_loads_memory(self, temp_dir):
        MemoryStore(temp_dir).append("session-A", "DRY principle enforced")
        cm = ContextManager(
            AppSettings(
                max_context_tokens=DEFAULT_CONTEXT_WINDOW,
                repo_map_enabled=False,
                home_dir=str(temp_dir / "test.db"),
                workspace_root=str(temp_dir),
            )
        )
        memory_text = cm.get_memory()
        assert "DRY principle enforced" in memory_text


class TestProjectMemory:
    def test_append_project_creates_file(self, temp_dir):
        store = MemoryStore(temp_dir)
        path = store.append_project("All configs live in config/")
        assert path.exists()
        assert path.name == "PROJECT.md"
        assert "config/" in path.read_text(encoding="utf-8")

    def test_append_project_accumulates(self, temp_dir):
        store = MemoryStore(temp_dir)
        store.append_project("Use pytest for tests")
        store.append_project("Use ruff for linting")
        text = (store.dir / "PROJECT.md").read_text(encoding="utf-8")
        assert "pytest" in text
        assert "ruff" in text

    def test_load_includes_project_memory_first(self, temp_dir):
        store = MemoryStore(temp_dir)
        store.append_project("Project uses FastAPI")
        store.append("sess-1", "Session fact")
        loaded = MemoryStore(temp_dir).load()
        assert loaded.index("FastAPI") < loaded.index("Session fact")
        assert "PROJECT.md" in loaded

    def test_load_plain_includes_project_first(self, temp_dir):
        store = MemoryStore(temp_dir)
        store.append_project("Cross-session rule: no globals")
        store.append("sess-1", "Local fact")
        plain = MemoryStore(temp_dir).load_plain()
        assert plain.index("no globals") < plain.index("Local fact")

    def test_project_rollover_caps_file_size(self, temp_dir):
        store = MemoryStore(temp_dir, max_chars=200)
        store.append_project("x" * 500)
        store.append_project("y" * 500)
        assert len((store.dir / "PROJECT.md").read_text(encoding="utf-8")) <= 260

    def test_empty_project_facts_does_not_write(self, temp_dir):
        store = MemoryStore(temp_dir)
        store.append_project("   ")
        assert not (store.dir / "PROJECT.md").exists()
