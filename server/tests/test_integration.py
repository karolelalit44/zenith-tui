from pathlib import Path

import pytest

from server.agents.context import ContextManager
from server.agents.loop import AgentLoop
from server.agents.recovery import RecoverableAgentLoop
from server.api.shutdown import GracefulShutdown
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.domain.events import Event, EventKind
from server.domain.message import Message
from server.domain.session import Session
from server.persistence.connection import Database
from server.providers.base import BaseProvider
from server.providers.registry import ProviderRegistry
from server.sessions.export import SessionExporter
from server.skills.loader import SkillLoader
from server.toolkit import create_default_registry
from server.workspace.repo_map import RepoMap
from server.workspace.tracker import FileTracker


class EchoProvider(BaseProvider):
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

    async def stream(
        self, messages: list[dict], tools=None, tool_choice=None, response_format=None
    ):
        response = await self.complete(messages)
        for char in response:
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["test-model"]


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
        kinds = [e.kind for e in events]
        assert EventKind.THINKING in kinds
        assert EventKind.TOOL_CALL in kinds or EventKind.SUCCESS in kinds

    @pytest.mark.asyncio
    async def test_plan_mode_blocks_write_tools(self, test_config):
        provider = EchoProvider()
        tool_registry = create_default_registry()
        AgentLoop(test_config, provider, tool_registry=tool_registry)
        result = await tool_registry.execute(
            "file_write", {"path": "x", "content": "y"}, ".", mode="plan"
        )
        assert not result.success
        assert "not available" in result.error


class TestErrorRecovery:
    @pytest.mark.asyncio
    async def test_recovers_from_provider_error(self, test_config):
        class FailingProvider(BaseProvider):
            def __init__(self):
                super().__init__("fail", "fail-model")

            async def complete(self, messages, tools=None):
                raise RuntimeError("API down")

            async def stream(self, messages, tools=None):
                yield ("should not reach", None)
                raise RuntimeError("API down")

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
        from server.domain.errors import ProviderError

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
        [e for e in events if e.kind == EventKind.WARNING]
        assert len(error_events) >= 1
        assert any(e.data.get("recoverable") is True for e in error_events)

    @pytest.mark.asyncio
    async def test_recoverable_agent_loop_accepts_repo_map(self, test_config):
        class DummyProvider(BaseProvider):
            def __init__(self):
                super().__init__("dummy", "dummy-model")

            async def complete(self, messages, tools=None):
                return "OK"

            async def stream(self, messages, tools=None):
                yield ("OK", None)

            async def validate(self):
                return True

            async def list_models(self):
                return []

        agent = RecoverableAgentLoop(test_config, DummyProvider())
        events = []
        async for event in agent.process_prompt("Test", "s1", [], mode="plan", repo_map=""):
            events.append(event)


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
        messages = [Message(session_id=session.id, role="user", content="Test")]
        filepath = exporter.export(session, messages, str(temp_dir / "exports"))
        assert Path(filepath).exists()
        content = Path(filepath).read_text()
        assert "File Export" in content

    def test_export_with_events(self):
        exporter = SessionExporter()
        session = Session(title="Events Test")
        events = [
            Event(kind=EventKind.THINKING, data={"text": "Thinking..."}),
            Event(
                kind=EventKind.TOOL_RESULT,
                data={"tool": "file_write", "success": True, "metadata": {"path": "new.py"}},
            ),
            Event(kind=EventKind.ERROR, data={"message": "Something failed"}),
        ]
        messages = [
            Message(session_id=session.id, role="assistant", content="Result", events=events)
        ]
        md = exporter.export_to_string(session, messages)
        assert "Thinking" in md
        assert "tool_result" in md or "new.py" in md


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
        assert "skills/test-skill" in prompt

    def test_skill_names(self, temp_dir):
        for name in ["alpha", "beta"]:
            d = temp_dir / "skills" / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"# {name}")
        loader = SkillLoader(str(temp_dir))
        names = loader.get_skill_names()
        assert any("alpha" in n for n in names)
        assert any("beta" in n for n in names)

    def test_skip_hidden_dirs(self, temp_dir):
        hidden = temp_dir / ".hidden" / "skill"
        hidden.mkdir(parents=True)
        (hidden / "SKILL.md").write_text("# Hidden")
        loader = SkillLoader(str(temp_dir))
        skills = loader.find_skills()
        assert len(skills) == 0

    def test_ignores_skills_outside_skill_dirs(self, temp_dir):
        stray = temp_dir / "lib" / "vendor" / "skill"
        stray.mkdir(parents=True)
        (stray / "SKILL.md").write_text("# Stray")
        loader = SkillLoader(str(temp_dir))
        assert loader.find_skills() == []

    def test_skill_prompt_is_metadata_only(self, temp_dir):
        skills_dir = temp_dir / "skills" / "test-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "# Test\n\nA long body that must not be embedded verbatim."
        )
        loader = SkillLoader(str(temp_dir))
        prompt = loader.get_skill_prompt()
        assert "Loaded Skills" in prompt
        assert "skills/test-skill/SKILL.md" in prompt
        assert "long body that must not be embedded verbatim" not in prompt


class TestFileTrackerIntegration:
    def test_tracks_tool_operations(self):
        tracker = FileTracker(".")
        tracker.track("new.py", "create", "print('hello')")
        tracker.track("old.py", "edit", "old content")
        tracker.track("del.py", "delete")
        assert tracker.has_changes()
        assert len(tracker.get_changed_files()) == 3
        assert "create" in tracker.get_summary()


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
        assert len(called) == 1


class TestContextManagerIntegration:
    def test_build_messages_with_long_history(self, test_config):
        test_config.max_context_tokens = 5000
        ctx = ContextManager(test_config)
        history = [
            Message(session_id="s1", role="user", content=f"Message {i}: " + "word " * 200)
            for i in range(100)
        ]
        messages = ctx.build_messages(history, "System.", "New.", "gpt-4")
        assert len(messages) < 102
        assert messages[-1]["content"] == "New."


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
