"""Integration tests for CaptainOrchestrator.investigate — full delegation pathway."""

import json

import pytest

from server.agents.delegation import CodebaseScout
from server.agents.delegation.orchestrator import CaptainOrchestrator
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.domain.session import Session
from server.storage.session_store import FileMessageRepository, FileSessionRepository
from server.providers.base import BaseProvider
from server.toolkit import create_default_registry


def _scout_json() -> str:
    payload = {
        "task_id": "ignored",
        "agent_id": "ignored",
        "status": "completed",
        "summary": "Sessions persist in SQLite through SessionRepository.",
        "findings": [
            {
                "claim": "Session rows live in SQLite",
                "confidence": "verified",
                "evidence_refs": ["0"],
            }
        ],
        "evidence": [
            {"type": "file_read", "path": "notes.txt", "snippet": "sessions table"}
        ],
        "affected_files": [],
        "proposed_changes": [],
        "unverified": [],
        "blocked": [],
    }
    return "```json\n" + json.dumps(payload) + "\n```"


class _ScoutProvider(BaseProvider):
    def __init__(self, final_text: str | None = None, fail: bool = False):
        super().__init__("captainscript", "captain-model")
        self.call_count = 0
        self.final_text = final_text
        self.fail = fail

    async def complete(self, messages, tools=None):
        self.call_count += 1
        if self.fail:
            raise RuntimeError("scout provider exploded")
        if self.call_count == 1:
            return '```tool\n{"tool": "file_read", "params": {"path": "notes.txt"}}\n```'
        return self.final_text or _scout_json()

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        text = await self.complete(messages, tools)
        for char in text:
            yield (char, None)

    async def validate(self):
        return True

    async def list_models(self):
        return ["captain-model"]


DEMO_PROMPT = (
    "Investigate how sessions are persisted and what would need to change "
    "to migrate them from SQLite to JSONL"
)


@pytest.fixture
def test_config(temp_dir):
    return AppSettings(
        home_dir=str(temp_dir),
        workspace_root=str(temp_dir),
    )


@pytest.fixture
def home(test_config):
    from server.storage import StorageHome, ensure_materialized

    h = StorageHome(test_config.home_dir)
    ensure_materialized(h)
    return h


@pytest.fixture
def repos(home):
    return FileSessionRepository(home), FileMessageRepository(home)


@pytest.fixture
def workspace(temp_dir):
    (temp_dir / "notes.txt").write_text("sessions table")
    return temp_dir


def _stages(events):
    return [
        e.data.get("stage")
        for e in events
        if e.kind == EventKind.AGENT_ORCHESTRATION
    ]


class TestLifecycleEvents:
    @pytest.mark.asyncio
    async def test_stage_sequence_and_raw_kinds_in_order(
        self, test_config, home, repos, workspace
    ):
        session_repo, message_repo = repos
        parent = await session_repo.create(Session(title="lifecycle"))
        provider = _ScoutProvider()
        orchestrator = CaptainOrchestrator(
            test_config,
            provider,
            create_default_registry(),
            session_repo=session_repo,
            message_repo=message_repo,
        )
        events = []
        async for event in orchestrator.investigate(DEMO_PROMPT, CodebaseScout, parent.id):
            events.append(event)

        stages = _stages(events)
        # lifecycle stages appear in order (subsequence: extras allowed between)
        idx = {stage: i for i, stage in enumerate(stages)}
        assert "thinking" in idx
        assert "delegating" in idx
        assert "working" in idx
        assert "complete" in idx
        assert idx["thinking"] < idx["delegating"] < idx["working"] < idx["complete"]

        kinds = [e.kind for e in events]
        # raw kinds alongside: spawned right after delegating, status while working,
        # complete before terminal success
        spawn_idx = kinds.index(EventKind.AGENT_SPAWNED)
        assert kinds[spawn_idx - 1] == EventKind.AGENT_ORCHESTRATION
        assert events[spawn_idx - 1].data.get("stage") == "delegating"
        assert kinds.index(EventKind.AGENT_SPAWNED) < kinds.index(EventKind.AGENT_STATUS)
        complete_idx = kinds.index(EventKind.AGENT_COMPLETE)
        assert kinds[complete_idx + 1] == EventKind.AGENT_ORCHESTRATION
        assert kinds[-1] == EventKind.SUCCESS

    @pytest.mark.asyncio
    async def test_working_events_capped_at_three(self, test_config, home, repos, workspace):
        session_repo, message_repo = repos
        parent = await session_repo.create(Session(title="capped"))
        orchestrator = CaptainOrchestrator(
            test_config,
            _ScoutProvider(),
            create_default_registry(),
            session_repo=session_repo,
            message_repo=message_repo,
        )
        events = []
        async for event in orchestrator.investigate(DEMO_PROMPT, CodebaseScout, parent.id):
            events.append(event)
        working = [
            e
            for e in events
            if e.kind == EventKind.AGENT_ORCHESTRATION
            and e.data.get("stage") == "working"
        ]
        assert 1 <= len(working) <= 3

    @pytest.mark.asyncio
    async def test_crewmate_id_stable_across_stages(self, test_config, home, repos, workspace):
        session_repo, message_repo = repos
        parent = await session_repo.create(Session(title="stable-id"))
        orchestrator = CaptainOrchestrator(
            test_config,
            _ScoutProvider(),
            create_default_registry(),
            session_repo=session_repo,
            message_repo=message_repo,
        )
        events = []
        async for event in orchestrator.investigate(DEMO_PROMPT, CodebaseScout, parent.id):
            events.append(event)
        ids_by_stage = {}
        for e in events:
            if e.kind == EventKind.AGENT_ORCHESTRATION and e.data.get("crewmates"):
                stage = e.data["stage"]
                ids_by_stage.setdefault(stage, set()).update(
                    cm["id"] for cm in e.data["crewmates"]
                )
        all_ids = set().union(*ids_by_stage.values())
        assert len(all_ids) == 1
        crewmate_id = next(iter(all_ids))
        assert crewmate_id.startswith("codebase-scout:")
        assert len(crewmate_id.split(":")[1]) == 8


class TestIsolationAndPersistence:
    @pytest.mark.asyncio
    async def test_child_session_created_with_parent_link(
        self, test_config, home, repos, workspace
    ):
        session_repo, message_repo = repos
        parent = await session_repo.create(Session(title="linked"))
        orchestrator = CaptainOrchestrator(
            test_config,
            _ScoutProvider(),
            create_default_registry(),
            session_repo=session_repo,
            message_repo=message_repo,
        )
        async for _ in orchestrator.investigate(DEMO_PROMPT, CodebaseScout, parent.id):
            pass
        children = [
            s for s in await session_repo.list_all() if s.parent_session_id == parent.id
        ]
        assert len(children) == 1
        assert children[0].title.startswith("scout-")

    @pytest.mark.asyncio
    async def test_child_message_persisted_and_parent_counters_updated(
        self, test_config, home, repos, workspace
    ):
        session_repo, message_repo = repos
        parent = await session_repo.create(Session(title="persisting"))
        orchestrator = CaptainOrchestrator(
            test_config,
            _ScoutProvider(final_text=_scout_json()),
            create_default_registry(),
            session_repo=session_repo,
            message_repo=message_repo,
        )
        async for _ in orchestrator.investigate(DEMO_PROMPT, CodebaseScout, parent.id):
            pass
        child = next(
            s for s in await session_repo.list_all() if s.parent_session_id == parent.id
        )
        messages = await message_repo.get_by_session(child.id)
        assistant = [m for m in messages if m.role == "assistant"]
        assert assistant, "child assistant message must be persisted"
        assert "SessionRepository" in assistant[0].content

        updated_parent = await session_repo.get(parent.id)
        assert updated_parent.message_count == 1
        assert updated_parent.total_tokens >= 0


class TestDuplicateDetection:
    @pytest.mark.asyncio
    async def test_duplicate_hit_skips_run(self, test_config, home, repos, workspace):
        session_repo, message_repo = repos
        parent = await session_repo.create(Session(title="dedupe"))
        provider = _ScoutProvider()
        orchestrator = CaptainOrchestrator(
            test_config,
            provider,
            create_default_registry(),
            session_repo=session_repo,
            message_repo=message_repo,
        )
        first = []
        async for event in orchestrator.investigate(DEMO_PROMPT, CodebaseScout, parent.id):
            first.append(event)
        calls_after_first = provider.call_count
        assert calls_after_first >= 2

        second = []
        async for event in orchestrator.investigate(DEMO_PROMPT, CodebaseScout, parent.id):
            second.append(event)

        assert provider.call_count == calls_after_first, "cached hit must not re-run"
        assert orchestrator.last_result.status == "cached"
        second_kinds = [e.kind for e in second]
        assert EventKind.AGENT_SPAWNED not in second_kinds
        assert EventKind.AGENT_COMPLETE in second_kinds
        assert second_kinds[-1] == EventKind.SUCCESS
        assert "thinking" not in _stages(second)
        assert "complete" in _stages(second)
        # no extra child session was created for the cached hit
        children = [
            s for s in await session_repo.list_all() if s.parent_session_id == parent.id
        ]
        assert len(children) == 1


class TestFailedScout:
    @pytest.mark.asyncio
    async def test_failed_scout_emits_failed_complete_stage_and_terminal_success(
        self, test_config, home, repos, workspace
    ):
        session_repo, message_repo = repos
        parent = await session_repo.create(Session(title="failing"))
        orchestrator = CaptainOrchestrator(
            test_config,
            _ScoutProvider(fail=True),
            create_default_registry(),
            session_repo=session_repo,
            message_repo=message_repo,
        )
        events = []
        async for event in orchestrator.investigate(DEMO_PROMPT, CodebaseScout, parent.id):
            events.append(event)

        assert orchestrator.last_result.status == "failed"
        kinds = [e.kind for e in events]
        assert EventKind.AGENT_FAILED in kinds
        failed_event = next(e for e in events if e.kind == EventKind.AGENT_FAILED)
        assert "exploded" in failed_event.data.get("error", "")
        complete_orch = [
            e
            for e in events
            if e.kind == EventKind.AGENT_ORCHESTRATION and e.data.get("stage") == "complete"
        ]
        assert complete_orch
        crewmates = complete_orch[-1].data["crewmates"]
        assert crewmates[0]["status"] == "failed"
        plan_items = complete_orch[-1].data["plan"]
        assert plan_items[0]["status"] == "failed"
        assert kinds[-1] == EventKind.SUCCESS
