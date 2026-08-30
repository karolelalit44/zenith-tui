"""Integration/regression tests: PromptExecutor delegation route.

Pins three behaviors:
1. a capability-matching prompt routes through CaptainOrchestrator;
2. a non-matching prompt falls through to the normal agent loop unchanged;
3. the plan->build CrewmateLoop handoff is byte-for-byte unaffected — and
   survives its early-return `finally` block (the UnboundLocalError fix).
"""

from datetime import datetime
import json

import pytest

from server.agents.prompt_executor import PromptExecutor
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.domain.session import Session
from server.providers.base import BaseProvider
from server.skills.loader import SkillLoader
from server.storage.session_store import FileMessageRepository, FileSessionRepository
from server.toolkit import create_default_registry

DEMO_PROMPT = (
    "Investigate how sessions are persisted and determine what would need "
    "to change to migrate them from SQLite to JSONL"
)


def _crewmate_json() -> str:
    payload = {
        "task_id": "ignored",
        "agent_id": "ignored",
        "status": "completed",
        "summary": "Sessions persist in SQLite through SessionRepository.",
        "findings": [],
        "evidence": [{"type": "file_read", "path": "notes.txt", "snippet": "sessions table"}],
    }
    return "```json\n" + json.dumps(payload) + "\n```"


class _FakeManager:
    def __init__(self):
        self.events = []

    async def send_event(self, session_id, event, **kwargs):
        self.events.append(event)


class _PlainOrCrewmateProvider(BaseProvider):
    """Explicit state machine: normal-loop text vs the delegated crewmate script.

    Phase entry is keyed on ``OUTPUT CONTRACT`` — a marker that only exists
    inside ``build_crewmate_prompt`` — never on cross-message content matching.
    """

    def __init__(self):
        super().__init__("dual", "dual-model")
        self.call_count = 0
        self.mission_active = False

    @staticmethod
    def _flatten(messages) -> str:
        parts = []
        for m in messages:
            content = m.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                parts.extend(str(part) for part in content)
            else:
                parts.append(str(content))
        return "\n".join(parts)

    async def complete(self, messages, tools=None):
        self.call_count += 1
        transcript = self._flatten(messages)
        if not self.mission_active:
            if "OUTPUT CONTRACT" in transcript:
                self.mission_active = True
                return '```tool\n{"tool": "file_read", "params": {"path": "notes.txt"}}\n```'
            return "Task complete."
        if "[Tool:" in transcript:
            return _crewmate_json()
        return "Investigation finished without further reads."

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        text = await self.complete(messages, tools)
        for char in text:
            yield (char, None)

    async def validate(self):
        return True

    async def list_models(self):
        return ["dual-model"]


@pytest.fixture
def test_config(temp_dir):
    # 'proactive' exercises the pre-loop Captain route (the default 'tool'
    # governance deliberately reserves delegation for the mid-turn tool).
    return AppSettings(
        home_dir=str(temp_dir),
        workspace_root=str(temp_dir),
        explore_delegation="proactive",
    )


@pytest.fixture
def storage_home(test_config):
    from server.storage import StorageHome, ensure_materialized

    h = StorageHome(test_config.home_dir)
    ensure_materialized(h)
    return h


@pytest.fixture
def executor(test_config, storage_home):
    session_repo = FileSessionRepository(storage_home)
    message_repo = FileMessageRepository(storage_home)
    ex = PromptExecutor(
        test_config,
        _PlainOrCrewmateProvider(),
        create_default_registry(),
        session_repo,
        message_repo,
        SkillLoader(str(test_config.workspace_root)),
    )
    ex._session_repo = session_repo
    ex._message_repo = message_repo
    return ex


@pytest.fixture
def workspace(temp_dir):
    (temp_dir / "notes.txt").write_text("sessions table")
    return temp_dir


class TestDelegationRoute:
    @pytest.mark.asyncio
    async def test_matching_prompt_routes_to_crewmate(self, executor, workspace):
        session = await executor._session_repo.create(Session(title="routed"))
        manager = _FakeManager()
        await executor._execute(session.id, DEMO_PROMPT, "build", None, manager)
        await executor._summary_scheduler.drain()

        kinds = [e.kind for e in manager.events]
        assert EventKind.CAPTAIN_ORCHESTRATION in kinds
        assert EventKind.CREWMATE_SPAWNED in kinds
        # C-F02 ordering: the executor holds back nothing on this path — our
        # success is followed by the end-of-run SESSION_SUMMARIZED snapshot.
        assert EventKind.SUCCESS in kinds
        assert EventKind.SESSION_SUMMARIZED in kinds

        # result summary becomes the persisted assistant response text
        messages = await executor._message_repo.get_by_session(session.id)
        assert any(m.role == "assistant" and "SessionRepository" in m.content for m in messages)

    @pytest.mark.asyncio
    async def test_governance_off_disables_pre_loop_route(
        self, test_config, storage_home, workspace
    ):
        """WP5 D3: explore_delegation='off' skips the Captain route entirely."""
        config = test_config.model_copy(update={"explore_delegation": "off"})
        session_repo = FileSessionRepository(storage_home)
        message_repo = FileMessageRepository(storage_home)
        ex = PromptExecutor(
            config,
            _PlainOrCrewmateProvider(),
            create_default_registry(),
            session_repo,
            message_repo,
            SkillLoader(str(config.workspace_root)),
        )
        ex._session_repo = session_repo
        ex._message_repo = message_repo

        session = await ex._session_repo.create(Session(title="governed"))
        manager = _FakeManager()
        await ex._execute(session.id, DEMO_PROMPT, "build", None, manager)
        await ex._summary_scheduler.drain()

        kinds = [e.kind for e in manager.events]
        assert EventKind.CAPTAIN_ORCHESTRATION not in kinds
        assert EventKind.CREWMATE_SPAWNED not in kinds
        assert EventKind.SUCCESS in kinds, "prompt falls through to the normal loop"

    @pytest.mark.asyncio
    async def test_matching_prompt_is_cached_on_second_send(self, executor, workspace):
        session = await executor._session_repo.create(Session(title="cached"))
        first_manager = _FakeManager()
        await executor._execute(session.id, DEMO_PROMPT, "build", None, first_manager)
        await executor._summary_scheduler.drain()
        calls_after_first = executor._provider.call_count

        second_manager = _FakeManager()
        await executor._execute(session.id, DEMO_PROMPT, "build", None, second_manager)
        await executor._summary_scheduler.drain()
        assert executor._provider.call_count == calls_after_first
        kinds = [e.kind for e in second_manager.events]
        assert EventKind.CAPTAIN_ORCHESTRATION in kinds
        assert EventKind.CREWMATE_SPAWNED not in kinds


class TestNormalLoopFallthrough:
    @pytest.mark.asyncio
    async def test_non_matching_prompt_takes_normal_loop(self, executor, workspace):
        session = await executor._session_repo.create(Session(title="normal"))
        manager = _FakeManager()
        await executor._execute(session.id, "hello there friend", "build", None, manager)
        await executor._summary_scheduler.drain()

        kinds = [e.kind for e in manager.events]
        assert EventKind.CAPTAIN_ORCHESTRATION not in kinds
        assert EventKind.CREWMATE_SPAWNED not in kinds
        assert EventKind.SUCCESS in kinds


class TestCrewmateHandoffRegression:
    @pytest.mark.asyncio
    async def test_plan_build_handoff_unchanged_and_finally_safe(self, executor, workspace):
        """The CrewmateLoop trigger must be untouched — and its early-return
        path must no longer crash in the `finally` block (UnboundLocalError)."""
        session = await executor._session_repo.create(
            Session(
                title="handoff",
                plan_output="1. Implement persistence change\n2. Verify",
                plan_approved_at=datetime.now(),
            )
        )
        manager = _FakeManager()
        await executor._execute(
            session.id,
            "Implement the approved plan now",
            "build",
            None,
            manager,
        )
        await executor._summary_scheduler.drain()

        kinds = [e.kind for e in manager.events]
        assert EventKind.CAPTAIN_ORCHESTRATION not in kinds
        assert EventKind.SUCCESS in kinds
        # the Phase-0 fix: assistant message persisted after the early return
        messages = await executor._message_repo.get_by_session(session.id)
        assert any(m.role == "assistant" for m in messages)
