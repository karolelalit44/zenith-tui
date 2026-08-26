"""WP5 Phase 1-3: explore tool contracts.

Covers:
- Structured report rendering into a bounded parent-context payload (S2);
- child transcript isolation (D5);
- runtime custom crewmates with bounded parameters;
- governance gating (D3);
- rolling-window aggregate token budget (D6);
- hybrid model routing by thoroughness (D2);
- failed missions still return an actionable report;
- parent todo lifecycle is untouched by child missions.
"""

import pytest

from server.agents.delegation.agent_definition import build_custom_definition
from server.agents.todo_state import get_todo_state
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.providers.base import BaseProvider
from server.toolkit.tools.explore_tool import ExploreTool

_REPORT = """Investigation complete.

```json
{
  "task_id": "t1",
  "agent_id": "apogee",
  "status": "completed",
  "summary": "Compaction triggers at 85 percent context usage.",
  "findings": [
    {"claim": "Threshold gate lives in ContextManager", "confidence": "verified", "evidence_refs": ["0"]},
    {"claim": "Manual /compact reuses CompactionService", "confidence": "proposed", "evidence_refs": []}
  ],
  "evidence": [{"type": "file_read", "path": "server/agents/context.py", "snippet": "percent >= threshold"}],
  "affected_files": ["server/agents/context.py"],
  "unverified": ["token estimator rounding"],
  "blocked": []
}
```"""


class _ScoutScriptedProvider(BaseProvider):
    """Child turns are scripted; every prompt seen is recorded."""

    def __init__(self, final_reply: str | None = _REPORT, fail_child: bool = False):
        super().__init__("scout-test", "parent-model-x")
        self.prompts: list[str] = []
        self.models_seen: list[str] = []
        self.final_reply = final_reply
        self.fail_child = fail_child

    async def complete(self, messages, tools=None):
        content = " ".join(str(m.get("content", "")) for m in messages or [])
        self.prompts.append(content)
        self.models_seen.append(str(getattr(self, "model", "")))
        if self.fail_child:
            raise RuntimeError("child provider down")
        return self.final_reply or ""

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        response = await self.complete(messages)
        for char in response:
            yield (char, None)

    async def validate(self):
        return True

    async def list_models(self):
        return ["parent-model-x"]


@pytest.fixture(autouse=True)
def _fresh_explore_ledger():
    """The spend ledger is process-global; isolate it per test."""
    from server.toolkit.tools.explore_tool import _ledger

    _ledger._spend.clear()
    yield
    _ledger._spend.clear()


@pytest.fixture
def config(temp_dir):
    return AppSettings(
        providers={"test": ProviderConfig(model="parent-model-x", is_active=True)},
        active_provider="test",
        home_dir=str(temp_dir / "test.db"),
        workspace_root=str(temp_dir),
        weak_model="weak-model-y",
    )


def _tool(config, provider) -> ExploreTool:
    from server.toolkit import create_default_registry

    return ExploreTool(
        config=config,
        provider=provider,
        tool_registry=create_default_registry(),
        weak_model=config.weak_model,
    )


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def test_explore_returns_structured_summary_within_cap(config, temp_dir):
    provider = _ScoutScriptedProvider()
    result = _run(
        _tool(config, provider).execute({"objective": "how is compaction triggered"}, str(temp_dir))
    )

    assert result.success is True
    assert len(result.output) <= 2000 + 10
    assert "[explore] completed" in result.output
    assert "[verified] Threshold gate lives in ContextManager" in result.output
    meta = result.metadata
    assert meta["explore_status"] == "completed"
    assert meta["verified_count"] == 1
    assert meta["proposed_count"] == 1
    assert meta["agent_name"] == "Apogee"
    assert meta["tokens_used"] > 0


def test_child_transcript_stays_out_of_parent_context(config, temp_dir):
    marker = "INTERMEDIATE_CHILD_MARKER_XYZ"
    provider = _ScoutScriptedProvider(final_reply=f"Working notes {marker}.\n\n{_REPORT}")
    result = _run(_tool(config, provider).execute({"objective": "trace state"}, str(temp_dir)))

    # The child's pre-report chatter is part of its own transcript only; the
    # assembled structured report replaces it wholesale.
    assert marker not in result.output
    assert "Summary: Compaction triggers" in result.output


def test_custom_crewmate_runtime_params(config, temp_dir):
    provider = _ScoutScriptedProvider()
    params = {
        "objective": "find where session state persists",
        "crewmate": {
            "name": "Vasco",
            "role": "Persistence Analyst",
            "focus": "Prioritize storage adapters and profile stores.",
        },
    }
    result = _run(_tool(config, provider).execute(params, str(temp_dir)))

    assert result.metadata["agent_name"] == "Vasco"
    assert result.metadata["agent_role"] == "Persistence Analyst"
    joined = "\n".join(provider.prompts)
    assert "Crewmate focus: Prioritize storage adapters" in joined
    definition, focus = build_custom_definition(name="Vasco")
    assert definition.id.startswith("custom-")
    assert focus == ""  # no focus passed here
    # Structural constraints always hold for custom crewmates.
    assert definition.can_delegate is False


def test_custom_crewmate_pinned_model_overrides_routing(config, temp_dir):
    provider = _ScoutScriptedProvider()
    params = {
        "objective": "map entry points",
        "thoroughness": "deep",
        "crewmate": {"name": "Sniper", "model": "pin-model-z"},
    }
    _run(_tool(config, provider).execute(params, str(temp_dir)))
    assert provider.models_seen and all(m == "pin-model-z" for m in provider.models_seen)


def test_hybrid_model_routing_by_thoroughness(config, temp_dir):
    """Scout-phase model follows D2 routing; the parent-side enrichment call
    necessarily runs on the parent provider and is excluded here."""

    def scout_models(provider):
        return [m for m, p in zip(provider.models_seen, provider.prompts) if "OBJECTIVE:" in p]

    provider_quick = _ScoutScriptedProvider()
    _run(
        _tool(config, provider_quick).execute(
            {"objective": "quick lookup", "thoroughness": "quick"}, str(temp_dir)
        )
    )
    quick = scout_models(provider_quick)
    assert quick and all(m == "weak-model-y" for m in quick), quick

    provider_deep = _ScoutScriptedProvider()
    _run(
        _tool(config, provider_deep).execute(
            {"objective": "deep sweep", "thoroughness": "deep"}, str(temp_dir)
        )
    )
    deep = scout_models(provider_deep)
    assert deep and all(m == "parent-model-x" for m in deep), deep


def test_governance_off_refuses_without_provider_calls(temp_dir):
    config = AppSettings(
        providers={"test": ProviderConfig(model="m", is_active=True)},
        active_provider="test",
        home_dir=str(temp_dir / "db"),
        workspace_root=str(temp_dir),
        explore_delegation="off",
    )
    provider = _ScoutScriptedProvider()
    result = _run(_tool(config, provider).execute({"objective": "x"}, str(temp_dir)))

    assert result.success is False
    assert "disabled" in (result.error or "").lower()
    assert provider.prompts == []


def test_token_budget_ledger_refuses_exhausted_window(config, temp_dir):
    """Real missions record spend; an exhausted window refuses up front."""
    from server.toolkit.tools.explore_tool import _ledger as global_ledger

    provider = _ScoutScriptedProvider()
    first = _run(_tool(config, provider).execute({"objective": "mission one"}, str(temp_dir)))
    assert first.success is True
    recorded = global_ledger.window_total()
    assert recorded > 0, "completed missions must feed the rolling-window ledger"
    calls_after_first = len(provider.prompts)

    # Simulate a window already at/over budget, then verify the refusal path.
    global_ledger.record(config.explore_token_budget)
    second = _run(_tool(config, provider).execute({"objective": "mission two"}, str(temp_dir)))
    assert second.success is False
    assert second.metadata["explore_status"] == "budget_exhausted"
    assert "budget" in (second.error or "").lower()
    assert provider.prompts, "first mission reached the provider"
    assert len(provider.prompts) == calls_after_first, (
        "refused mission must spend nothing - not even the enrichment pre-pass"
    )


def test_failed_mission_returns_actionable_report(config, temp_dir):
    provider = _ScoutScriptedProvider(fail_child=True)
    result = _run(_tool(config, provider).execute({"objective": "doomed"}, str(temp_dir)))

    assert result.success is False
    assert result.output.startswith("[explore] failed")
    assert "child provider down" in result.output
    assert result.metadata["explore_status"] == "failed"


def test_parent_todo_lifecycle_untouched_by_missions(config, temp_dir):
    parent_session = "parent-sess-todos"
    get_todo_state(parent_session).add("Implement caching layer")
    before = get_todo_state(parent_session).snapshot()

    provider = _ScoutScriptedProvider()
    _run(_tool(config, provider).execute({"objective": "survey persistence"}, str(temp_dir / "ws")))

    after = get_todo_state(parent_session).snapshot()
    assert (
        [t["title"] for t in before] == [t["title"] for t in after] == ["Implement caching layer"]
    )


# ---- WP6: objective enrichment pre-pass -----------------------------------


class _EnrichingProvider(_ScoutScriptedProvider):
    """Answers the instruction-builder pre-pass, then serves the scout."""

    def __init__(self):
        super().__init__()
        self.enrich_prompts: list[str] = []

    async def complete(self, messages, tools=None):
        content = str(messages[-1].get("content", "")) if messages else ""
        if content.startswith("Rewrite this codebase investigation"):
            self.enrich_prompts.append(content)
            return (
                "Deliverable: file:line list of every compaction trigger site "
                "plus the threshold constant definition."
            )
        return await super().complete(messages, tools)


def test_vague_objective_is_enriched_before_dispatch(config, temp_dir):
    provider = _EnrichingProvider()
    result = _run(_tool(config, provider).execute({"objective": "compaction stuff"}, str(temp_dir)))
    assert result.success
    assert len(provider.enrich_prompts) == 1, "short vague objectives must be enriched"


def test_detailed_objective_skips_enrichment(config, temp_dir):
    provider = _EnrichingProvider()
    detailed = (
        "Locate every site where context compaction triggers, map the threshold "
        "constants that gate it, and list the affected files with line numbers."
    )
    _run(_tool(config, provider).execute({"objective": detailed}, str(temp_dir)))
    assert provider.enrich_prompts == [], "task-shaped objectives skip the pre-pass"


# ---- WP5 Phase 4b: parallel fan-out ---------------------------------------


def test_parallel_fanout_runs_batch_and_merges_duplicates(config, temp_dir):
    """Two distinct explores dispatch concurrently; an identical third merges.

    Functional contract (perf claim documented, not asserted here):
    - both distinct missions execute and BOTH tool results reach the loop;
    - the duplicate is merged with an in-band note, not re-spent;
    - turn completes successfully.
    """
    import asyncio

    from server.agents.loop import AgentLoop
    from server.domain.events import EventKind
    from server.toolkit import create_default_registry

    class _FanoutProvider(BaseProvider):
        """Parent asks for three explores (two distinct + one dup) at once;
        child missions get the standard scripted report."""

        def __init__(self):
            super().__init__("fan", "fan-model")
            self.parent_calls = 0
            self.prompts: list[str] = []

        @staticmethod
        def _flatten(messages) -> str:
            parts = []
            for m in messages or []:
                c = m.get("content")
                parts.append(c if isinstance(c, str) else str(c))
            return "\n".join(parts)

        async def complete(self, messages, tools=None):
            flat = self._flatten(messages)
            self.prompts.append(flat)
            if "OUTPUT CONTRACT" in flat:
                return _REPORT
            return "All scouts have reported; synthesis follows."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            flat = self._flatten(messages)
            if (
                "OBJECTIVE:" not in flat
                and "OUTPUT CONTRACT" not in flat
                and self.parent_calls == 0
            ):
                self.parent_calls += 1
                reply = (
                    '```tool\n{"tool": "explore", "params": {"objective": "map auth flow"}}\n'
                    '{"tool": "explore", "params": {"objective": "map storage layer"}}\n'
                    '{"tool": "explore", "params": {"objective": "map auth flow"}}\n```'
                )
            else:
                reply = await self.complete(messages)
            for char in reply:
                yield (char, None)

        async def validate(self):
            return True

        async def list_models(self):
            return ["fan-model"]

    provider = _FanoutProvider()
    agent = AgentLoop(
        config,
        provider,
        tool_registry=create_default_registry(provider=provider, config=config),
    )

    async def collect():
        return [ev async for ev in agent.process_prompt("Investigate", "s1", [], "build")]

    events = asyncio.run(collect())

    explore_results = [
        e for e in events if e.kind == EventKind.TOOL_RESULT and e.data.get("tool") == "explore"
    ]
    assert len(explore_results) >= 2, "both distinct missions must produce results"
    assert events[-1].kind == EventKind.SUCCESS
    # The merged duplicate must NOT spawn a third child mission — the whole
    # point of fan-out dedupe is avoiding duplicate spend.
    child_missions = [p for p in provider.prompts if "OUTPUT CONTRACT" in p]
    assert len(child_missions) == 2, f"expected 2 scout missions, got {len(child_missions)}"
