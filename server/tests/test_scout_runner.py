"""Integration tests for the Apogee crewmate runner (read-only mission mechanics)."""

import json

import pytest

from server.agents.delegation import ApogeeCrewmate
from server.agents.delegation.scout import (
    FORWARDABLE_KINDS,
    CrewmateReadOnlyGuard,
    CrewmateRun,
    assemble_result,
    build_crewmate_prompt,
    register_crewmate_guard,
    run_crewmate,
)
from server.agents.delegation.task_envelope import build_task_envelope
from server.config.constants import READ_ONLY_TOOLS, CREWMATE_GRAPH_TOOLS, CREWMATE_MODE
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.providers.base import BaseProvider
from server.toolkit import create_default_registry


def _final_answer() -> str:
    payload = {
        "task_id": "ignored-by-assembler",
        "agent_id": "ignored-by-assembler",
        "status": "completed",
        "summary": "Sessions persist through SessionRepository backed by SQLite.",
        "findings": [
            {
                "claim": "Sessions are stored in SQLite",
                "confidence": "verified",
                "evidence_refs": ["0"],
            },
            {"claim": "JSONL would require rewriting the repos", "confidence": "proposed"},
        ],
        "evidence": [
            {
                "type": "file_read",
                "path": "notes.txt",
                "snippet": "SQLite session store",
            }
        ],
        "affected_files": ["server/persistence/repositories/sessions.py"],
        "proposed_changes": ["Introduce a storage backend interface"],
        "unverified": [],
        "blocked": [],
    }
    return "Investigation complete.\n\n```json\n" + json.dumps(payload) + "\n```\n"


class _ScriptedCrewmateProvider(BaseProvider):
    """Step 1: one real read tool call. Step 2: the AgentResult JSON block."""

    def __init__(self, final_text: str | None = None, fail: bool = False):
        super().__init__("crewmatescript", "crewmate-model")
        self.call_count = 0
        self.tool_names_seen: list[list[str]] = []
        self.modes_seen: list[str] = []
        self.final_text = final_text
        self.fail = fail

    async def complete(self, messages, tools=None):
        self.call_count += 1
        if self.fail:
            raise RuntimeError("crewmate provider exploded")
        if self.call_count == 1:
            return '```tool\n{"tool": "file_read", "params": {"path": "notes.txt"}}\n```'
        return self.final_text or "no findings"

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        if tools:
            self.tool_names_seen.append(list(tools))
        text = await self.complete(messages, tools)
        for char in text:
            yield (char, None)

    async def validate(self):
        return True

    async def list_models(self):
        return ["crewmate-model"]


@pytest.fixture
def test_config(temp_dir):
    return AppSettings(
        home_dir=str(temp_dir / "crewmate.db"),
        workspace_root=str(temp_dir),
    )


@pytest.fixture
def workspace(temp_dir):
    (temp_dir / "notes.txt").write_text("SQLite session store\nsessions table")
    return temp_dir


def _make_task(session_id: str = "child-1"):
    task = build_task_envelope(
        objective="Investigate how sessions are persisted and what a JSONL migration would change",
        definition=ApogeeCrewmate,
        session_id="parent-1",
        max_context_tokens=64_000,
    )
    task.child_session_id = session_id
    return task


async def _collect_crewmate(config, provider, task, registry=None):
    run = CrewmateRun()
    events = []
    async for event in run_crewmate(
        config=config,
        provider=provider,
        tool_registry=registry or create_default_registry(),
        task=task,
        definition=ApogeeCrewmate,
        run=run,
    ):
        events.append(event)
    return run, events


class TestEvidenceBackedFindings:
    @pytest.mark.asyncio
    async def test_scripted_read_produces_verified_findings(self, test_config, workspace):
        provider = _ScriptedCrewmateProvider(final_text=_final_answer())
        run, _events = await _collect_crewmate(test_config, provider, _make_task(), None)
        assert run.response_text.strip(), "final answer must be captured"
        result = assemble_result(_make_task(), ApogeeCrewmate, run)
        assert result.status == "completed"
        assert "SessionRepository" in result.summary
        assert result.findings[0].confidence == "verified"
        assert result.findings[0].claim == "Sessions are stored in SQLite"
        assert result.evidence[0].path == "notes.txt"
        assert "SQLite session store" in result.evidence[0].snippet
        assert result.affected_files == ["server/persistence/repositories/sessions.py"]
        assert result.proposed_changes
        # the real read actually happened against the workspace
        assert provider.call_count == 2
        assert run.tool_calls >= 1

    @pytest.mark.asyncio
    async def test_unparseable_output_becomes_unverified_fallback(self, test_config, workspace):
        provider = _ScriptedCrewmateProvider(final_text="plain prose, no json block")
        run, _ = await _collect_crewmate(test_config, provider, _make_task(), None)
        result = assemble_result(_make_task(), ApogeeCrewmate, run)
        assert result.status == "completed"
        assert result.unverified == [run.response_text.strip()]
        assert result.findings == []


class TestReadOnlyToolSurface:
    @staticmethod
    def _tool_name(tool) -> str | None:
        if isinstance(tool, str):
            return tool
        if isinstance(tool, dict):
            if tool.get("name"):
                return str(tool["name"])
            fn = tool.get("function")
            if isinstance(fn, dict) and fn.get("name"):
                return str(fn["name"])
        return None

    @pytest.mark.asyncio
    async def test_only_read_only_tools_offered_in_crewmate_mode(self, test_config, workspace):
        provider = _ScriptedCrewmateProvider(final_text=_final_answer())
        await _collect_crewmate(test_config, provider, _make_task(), create_default_registry())
        assert provider.tool_names_seen, "provider never received a tool surface"
        allowed = (
            set(READ_ONLY_TOOLS)
            | set(CREWMATE_GRAPH_TOOLS)
            | {"discover_capabilities", "get_tool_definition"}
        )
        offered = {
            name
            for names in provider.tool_names_seen
            for name in map(self._tool_name, names)
            if name
        }
        assert offered <= allowed
        assert offered, "tool extraction failed - no names recognized"
        assert "file_write" not in offered
        assert "bash" not in offered


class TestCrewmateReadOnlyGuard:
    @pytest.mark.asyncio
    async def test_guard_blocks_mutation_tools_in_crewmate_mode_end_to_end(self, workspace):
        registry = create_default_registry()
        guard = register_crewmate_guard(registry)

        from server.toolkit.base import ToolContext, ToolResult

        ctx = ToolContext(request_id="r1", mode=CREWMATE_MODE, workspace_root=str(workspace))

        blocked = await guard.before_execute("file_write", {}, ctx)
        assert isinstance(blocked, ToolResult)
        assert blocked.success is False
        assert "read-only" in blocked.error.lower()

        allowed = await guard.before_execute("file_read", {"path": "x"}, ctx)
        assert allowed is True

        build_ctx = ToolContext(request_id="r2", mode="build", workspace_root=str(workspace))
        assert await guard.before_execute("file_write", {}, build_ctx) is True

        # End-to-end through the shared registry even though file_write is not
        # mode-gated (requires_mode=None): the guard is the structural backstop.
        result = await registry.execute(
            "file_write",
            {"path": "hacked.txt", "content": "nope"},
            str(workspace),
            mode=CREWMATE_MODE,
        )
        assert result.success is False
        assert not (workspace / "hacked.txt").exists()

    def test_register_dedupes_by_type(self):
        registry = create_default_registry()
        first = register_crewmate_guard(registry)
        second = register_crewmate_guard(registry)
        assert first is second
        count = sum(
            1 for mw in getattr(registry, "_middleware", []) if isinstance(mw, CrewmateReadOnlyGuard)
        )
        assert count == 1


class TestInterceptedTerminals:
    @pytest.mark.asyncio
    async def test_success_intercepted_and_token_info_captured(self, test_config, workspace):
        provider = _ScriptedCrewmateProvider(final_text=_final_answer())
        run, events = await _collect_crewmate(test_config, provider, _make_task(), None)
        kinds = [e.kind for e in events]
        assert EventKind.SUCCESS not in kinds, "SUCCESS must be intercepted"
        assert EventKind.ERROR not in kinds
        assert set(FORWARDABLE_KINDS) & set(kinds), "forwardable child events were yielded"
        assert isinstance(run.token_info, dict)
        assert {"used", "total", "percent"} <= set(run.token_info.keys())
        result = assemble_result(_make_task(), ApogeeCrewmate, run)
        assert result.metrics.tokens_used >= 0
        assert result.metrics.iterations >= 1

    @pytest.mark.asyncio
    async def test_provider_error_captured_not_raised(self, test_config, workspace):
        provider = _ScriptedCrewmateProvider(fail=True)
        run, _events = await _collect_crewmate(test_config, provider, _make_task(), None)
        assert "exploded" in (run.last_error or "")
        result = assemble_result(
            _make_task(), ApogeeCrewmate, run, status="failed", error=run.last_error
        )
        assert result.status == "failed"
        assert "exploded" in (result.error or "")


class TestPromptContract:
    def test_build_crewmate_prompt_contains_contract(self):
        from server.agents.delegation.task_envelope import build_task_envelope as build

        task = build(
            objective="Trace session persistence",
            definition=ApogeeCrewmate,
            session_id="p",
            max_context_tokens=64_000,
            context_digest="captain knows: sqlite exists",
        )
        prompt = build_crewmate_prompt(task)
        assert "Trace session persistence" in prompt
        assert "READ-ONLY MANDATE" in prompt
        assert "OUTPUT CONTRACT" in prompt
        assert "EVIDENCE RULES" in prompt
        assert task.task_id in prompt
        assert "sqlite exists" in prompt
