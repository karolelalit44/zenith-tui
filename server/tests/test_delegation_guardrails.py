"""Guardrail unit tests: depth, child-per-run, context budget, timeout, isolation."""

import asyncio

import pytest

import server.agents.delegation.orchestrator as orch_module
from server.agents.delegation import (
    AGENT_TIMEOUT_SECONDS,
    MAX_DELEGATION_DEPTH,
    CREWMATE_CONTEXT_BUDGET_TOKENS,
    CaptainOrchestrator,
    ApogeeCrewmate,
)
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.domain.session import Session
from server.providers.base import BaseProvider
from server.storage.session_store import FileMessageRepository, FileSessionRepository


class _SleepProvider(BaseProvider):
    """Streams slowly enough to trip a (shortened) delegation timeout."""

    def __init__(self):
        super().__init__("sleepy", "sleepy-model")

    async def complete(self, messages, tools=None):
        await asyncio.sleep(1.0)
        return "still thinking"

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        response = await self.complete(messages, tools)
        yield (response, None)

    async def validate(self):
        return True

    async def list_models(self):
        return ["sleepy-model"]


class _ExplodingProvider(BaseProvider):
    def __init__(self):
        super().__init__("boom", "boom-model")

    async def complete(self, messages, tools=None):
        raise RuntimeError("provider exploded mid-crewmate")

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        response = await self.complete(messages, tools)
        yield (response, None)

    async def validate(self):
        return True

    async def list_models(self):
        return ["boom-model"]


class _InstantProvider(BaseProvider):
    def __init__(self, text="nothing to report"):
        super().__init__("inst", "inst-model")
        self.text = text

    async def complete(self, messages, tools=None):
        return self.text

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        text = await self.complete(messages, tools)
        yield (text, None)

    async def validate(self):
        return True

    async def list_models(self):
        return ["inst-model"]


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


class TestConstants:
    def test_guardrail_values_match_spec(self):
        assert MAX_DELEGATION_DEPTH == 1
        assert AGENT_TIMEOUT_SECONDS == 150
        assert CREWMATE_CONTEXT_BUDGET_TOKENS == 64_000
        assert ApogeeCrewmate.max_crewmates == 0
        assert ApogeeCrewmate.delegation_depth == 0


class TestDepthLimit:
    @pytest.mark.asyncio
    async def test_depth_beyond_limit_refused_without_child(self):
        orchestrator = CaptainOrchestrator(AppSettings(), _SleepProvider(), tool_registry=None)
        events = []
        async for event in orchestrator.investigate(
            "Investigate sessions", ApogeeCrewmate, "s-parent", depth=MAX_DELEGATION_DEPTH
        ):
            events.append(event)
        assert orchestrator.last_result is not None
        assert orchestrator.last_result.status == "failed"
        assert "depth" in (orchestrator.last_result.error or "").lower()
        assert any(e.kind == EventKind.ERROR for e in events)


class TestContextBudget:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("configured", "expected"),
        [
            (200_000, CREWMATE_CONTEXT_BUDGET_TOKENS),
            (16_000, 16_000),
        ],
    )
    async def test_budget_caps_into_crewmate_config(self, monkeypatch, temp_dir, configured, expected):
        captured = {}
        from server.agents import context as context_module

        real_cm = context_module.ContextManager

        def spying_cm(config):
            captured["max_context_tokens"] = config.max_context_tokens
            return real_cm(config)

        monkeypatch.setattr(context_module, "ContextManager", spying_cm)

        from server.agents.delegation.scout import CrewmateRun, run_crewmate
        from server.agents.delegation.task_envelope import build_task_envelope

        config = AppSettings(
            home_dir=str(temp_dir),
            workspace_root=str(temp_dir),
            max_context_tokens=configured,
        )
        task = build_task_envelope(
            objective="Investigate sessions",
            definition=ApogeeCrewmate,
            session_id=f"s-cap-{configured}",
            max_context_tokens=CREWMATE_CONTEXT_BUDGET_TOKENS,
        )
        task.child_session_id = f"child-cap-{configured}"

        async for _ in run_crewmate(
            config=config,
            provider=_InstantProvider(),
            tool_registry=None,
            task=task,
            definition=ApogeeCrewmate,
            run=CrewmateRun(),
        ):
            pass
        assert captured["max_context_tokens"] == expected


class TestTimeout:
    @pytest.mark.asyncio
    async def test_timeout_yields_timed_out_result_and_terminal_success(
        self, monkeypatch, test_config, home
    ):
        monkeypatch.setattr(orch_module, "AGENT_TIMEOUT_SECONDS", 0.05)
        session_repo = FileSessionRepository(home)
        message_repo = FileMessageRepository(home)
        parent = await session_repo.create(Session(title="timeout parent"))

        from server.toolkit import create_default_registry

        orchestrator = CaptainOrchestrator(
            test_config,
            _SleepProvider(),
            create_default_registry(),
            session_repo=session_repo,
            message_repo=message_repo,
        )
        events = []
        async for event in orchestrator.investigate(
            "Investigate how sessions are persisted and what would change over time",
            ApogeeCrewmate,
            parent.id,
        ):
            events.append(event)
        assert orchestrator.last_result.status == "timed_out"
        kinds = [e.kind for e in events]
        assert kinds.count(EventKind.CREWMATE_FAILED) == 1
        assert events[-1].kind == EventKind.SUCCESS


class TestFailureIsolation:
    @pytest.mark.asyncio
    async def test_provider_error_becomes_failed_result_not_exception(self, test_config, home):
        session_repo = FileSessionRepository(home)
        message_repo = FileMessageRepository(home)
        parent = await session_repo.create(Session(title="isolation parent"))

        from server.toolkit import create_default_registry

        orchestrator = CaptainOrchestrator(
            test_config,
            _ExplodingProvider(),
            create_default_registry(),
            session_repo=session_repo,
            message_repo=message_repo,
        )
        events = []
        async for event in orchestrator.investigate(
            "Investigate how sessions are persisted across the whole codebase today",
            ApogeeCrewmate,
            parent.id,
        ):
            events.append(event)
        assert orchestrator.last_result.status == "failed"
        assert "exploded" in (orchestrator.last_result.error or "")
        kinds = [e.kind for e in events]
        assert EventKind.CREWMATE_FAILED in kinds
        assert kinds[-1] == EventKind.SUCCESS
