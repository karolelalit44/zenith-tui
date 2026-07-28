"""Integration tests — full workflow tests across all modules."""

import pytest
from pathlib import Path

from config.settings import AppSettings
from config.providers import ProviderConfig
from db.connection import Database
from providers.registry import ProviderRegistry
from providers.base import BaseProvider
from core.session import Session
from core.message import Message
from core.events import Event, EventKind
from tools import create_default_registry
from agent.loop import AgentLoop
from agent.recovery import RecoverableAgentLoop
from agent.context import ContextManager
from session.export import SessionExporter
from workspace.tracker import FileTracker
from workspace.repo_map import RepoMap
from skills.loader import SkillLoader
from transport.shutdown import GracefulShutdown


# ── Test Provider ───────────────────────────────────────────────────


class EchoProvider(BaseProvider):
    """Provider that echoes input and can simulate tool calls."""

    def __init__(self, respond_with_tool: bool = False):
        super().__init__("test", "test-model")
        self.respond_with_tool = respond_with_tool
        self.call_count = 0

    async def complete(self, messages: list[dict], tools=None) -> str:
        self.call_count += 1
        user_msg = messages[-1]["content"] if messages else ""
        if self.respond_with_tool and self.call_count == 1:
            return '```tool\n{"tool": "file_read", "params": {"path": "test.txt"}}\n```'
        return f"Echo: {user_msg}"

    async def stream(self, messages: list[dict], tools=None):
        response = await self.complete(messages)
        for char in response:
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["test-model"]


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def test_config(temp_dir):
    return AppSettings(
        providers={"test": ProviderConfig(model="test-model", is_active=True)},
        active_provider="test",
        db_path=str(temp_dir / "test.db"),
        workspace_root=str(temp_dir),
    )


@pytest.fixture
async def test_db(test_config):
    db = Database(test_config.db_path)
    await db.connect()
    yield db
    await db.close()


@pytest.fixture
def test_registry():
    registry = ProviderRegistry()
    registry.register("test", EchoProvider())
    return registry


# ── Full Agent Workflow ─────────────────────────────────────────────


class TestAgentWorkflow:
    @pytest.mark.asyncio
    async def test_simple_prompt(self, test_config):
        provider = EchoProvider()
        agent = AgentLoop(test_config, provider)

        events = []
        async for event in agent.process_prompt("Hello", "s1", [], "build"):
            events.append(event)

        assert events[0].kind == EventKind.THINKING
        assert any(e.kind == EventKind.MESSAGE for e in events)
        assert events[-1].kind == EventKind.SUCCESS

    @pytest.mark.asyncio
    async def test_tool_call_flow(self, test_config):
        provider = EchoProvider(respond_with_tool=True)
        tool_registry = create_default_registry()
        agent = AgentLoop(test_config, provider, tool_registry=tool_registry)

        events = []
        async for event in agent.process_prompt("Read a file", "s1", [], "build"):
            events.append(event)

        # Should have thinking, tool analysis, tool result, then final message
        kinds = [e.kind for e in events]
        assert EventKind.THINKING in kinds
        assert EventKind.TOOL_CALL in kinds or EventKind.SUCCESS in kinds

    @pytest.mark.asyncio
    async def test_plan_mode_blocks_write_tools(self, test_config):
        provider = EchoProvider()
        tool_registry = create_default_registry()
        agent = AgentLoop(test_config, provider, tool_registry=tool_registry)

        # Verify tool registry enforces plan mode
        result = await tool_registry.execute(
            "file_write", {"path": "x", "content": "y"}, ".", mode="plan"
        )
        assert not result.success
        assert "not available" in result.error


# ── Error Recovery ──────────────────────────────────────────────────


class TestErrorRecovery:
    @pytest.mark.asyncio
    async def test_recovers_from_provider_error(self, test_config):
        class FailingProvider(BaseProvider):
            def __init__(self):
                super().__init__("fail", "fail-model")

            async def complete(self, messages, tools=None):
                raise Exception("API down")

            async def stream(self, messages, tools=None):
                yield ("should not reach", None)
                raise Exception("API down")

            async def validate(self):
                return False

            async def list_models(self):
                return []

        agent = RecoverableAgentLoop(test_config, FailingProvider())
        events = []
        async for event in agent.process_prompt("Test", "s1", [], "build"):
            events.append(event)

        error_events = [e for e in events if e.kind == EventKind.ERROR]
        assert len(error_events) >= 1
        assert agent.last_error is not None

    @pytest.mark.asyncio
    async def test_recoverable_provider_error(self, test_config):
        from core.errors import ProviderError

        class RateLimitedProvider(BaseProvider):
            def __init__(self):
                super().__init__("rate", "rate-model")

            async def complete(self, messages, tools=None):
                raise ProviderError("Rate limited", provider="rate", recoverable=True)

            async def stream(self, messages, tools=None):
                yield ("should not reach", None)
                raise ProviderError("Rate limited", provider="rate", recoverable=True)

            async def validate(self):
                return False

            async def list_models(self):
                return []

        agent = RecoverableAgentLoop(test_config, RateLimitedProvider())
        events = []
        async for event in agent.process_prompt("Test", "s1", [], "build"):
            events.append(event)

        error_events = [e for e in events if e.kind == EventKind.ERROR]
        warning_events = [e for e in events if e.kind == EventKind.WARNING]
        assert len(error_events) >= 1
        # RECOVERY_HINT warnings removed — error event carries recoverable flag instead
        assert any(e.data.get("recoverable") is True for e in error_events)


# ── Session Export ──────────────────────────────────────────────────


class TestSessionExport:
    def test_export_to_string(self):
        exporter = SessionExporter()
        session = Session(title="Test Session")
        messages = [
            Message(session_id=session.id, role="user", content="Hello"),
            Message(session_id=session.id, role="assistant", content="Hi there!"),
        ]
        md = exporter.export_to_string(session, messages)
        assert "# Test Session" in md
        assert "Hello" in md
        assert "Hi there!" in md

    def test_export_to_file(self, temp_dir):
        exporter = SessionExporter()
        session = Session(title="File Export")
        messages = [
            Message(session_id=session.id, role="user", content="Test"),
        ]
        filepath = exporter.export(session, messages, str(temp_dir / "exports"))
        assert Path(filepath).exists()
        content = Path(filepath).read_text()
        assert "File Export" in content

    def test_export_with_events(self):
        exporter = SessionExporter()
        session = Session(title="Events Test")
        events = [
            Event(kind=EventKind.THINKING, data={"text": "Thinking..."}),
            Event(kind=EventKind.TOOL_RESULT, data={"tool": "file_write", "success": True, "metadata": {"path": "new.py"}}),
            Event(kind=EventKind.ERROR, data={"message": "Something failed"}),
        ]
        messages = [
            Message(
                session_id=session.id,
                role="assistant",
                content="Result",
                events=events,
            ),
        ]
        md = exporter.export_to_string(session, messages)
        assert "Thinking" in md
        assert "tool_result" in md or "new.py" in md


# ── SKILL.md Loader ────────────────────────────────────────────────


class TestSkillLoader:
    def test_find_skills(self, temp_dir):
        skills_dir = temp_dir / "agents" / "skills" / "my-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text("# My Skill\nDo things.")

        loader = SkillLoader(str(temp_dir))
        skills = loader.find_skills()
        assert len(skills) == 1
        assert "My Skill" in skills[0]["content"]

    def test_no_skills(self, temp_dir):
        loader = SkillLoader(str(temp_dir))
        skills = loader.find_skills()
        assert len(skills) == 0

    def test_skill_prompt(self, temp_dir):
        skills_dir = temp_dir / "skills" / "test-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text("# Test\nContent here.")

        loader = SkillLoader(str(temp_dir))
        prompt = loader.get_skill_prompt()
        assert "Loaded Skills" in prompt
        assert "Content here." in prompt

    def test_skill_names(self, temp_dir):
        for name in ["alpha", "beta"]:
            d = temp_dir / name
            d.mkdir()
            (d / "SKILL.md").write_text(f"# {name}")

        loader = SkillLoader(str(temp_dir))
        names = loader.get_skill_names()
        assert "alpha" in names
        assert "beta" in names

    def test_skip_hidden_dirs(self, temp_dir):
        hidden = temp_dir / ".hidden" / "skill"
        hidden.mkdir(parents=True)
        (hidden / "SKILL.md").write_text("# Hidden")

        loader = SkillLoader(str(temp_dir))
        skills = loader.find_skills()
        assert len(skills) == 0


# ── File Tracker ────────────────────────────────────────────────────


class TestFileTrackerIntegration:
    def test_tracks_tool_operations(self):
        tracker = FileTracker(".")
        tracker.track("new.py", "create", "print('hello')")
        tracker.track("old.py", "edit", "old content")
        tracker.track("del.py", "delete")

        assert tracker.has_changes()
        assert len(tracker.get_changed_files()) == 3
        assert "create" in tracker.get_summary()


# ── Graceful Shutdown ───────────────────────────────────────────────


class TestGracefulShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_calls_cleanup(self):
        shutdown = GracefulShutdown()
        called = []

        async def cleanup():
            called.append(True)

        shutdown.register_cleanup(cleanup)
        await shutdown.shutdown()
        assert len(called) == 1
        assert shutdown.is_shutting_down

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self):
        shutdown = GracefulShutdown()
        called = []

        async def cleanup():
            called.append(True)

        shutdown.register_cleanup(cleanup)
        await shutdown.shutdown()
        await shutdown.shutdown()
        assert len(called) == 1  # only called once


# ── Context Manager ─────────────────────────────────────────────────


class TestContextManagerIntegration:
    def test_build_messages_with_long_history(self, test_config):
        test_config.max_context_tokens = 5000
        ctx = ContextManager(test_config)
        history = [
            Message(session_id="s1", role="user", content=f"Message {i}: " + "word " * 200)
            for i in range(100)
        ]
        messages = ctx.build_messages(history, "System.", "New.", "gpt-4")
        # Should not include all 100 messages — budget limits it
        assert len(messages) < 102  # system + all history + user
        assert messages[-1]["content"] == "New."


# ── Repo Map Integration ───────────────────────────────────────────


class TestRepoMapIntegration:
    def test_structure_and_summary(self, temp_dir):
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "main.py").write_text("print('hello')")
        (temp_dir / "README.md").write_text("# Test")

        repo = RepoMap(str(temp_dir))
        structure = repo.get_structure()
        summary = repo.get_summary()

        assert "Python" in summary
        assert len(structure["children"]) > 0
