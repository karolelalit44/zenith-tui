"""WP6 structural retrieval: symbol graph queries + mission brief + enrichment."""

import pytest

from server.config.constants import (
    ENRICH_DELIVERABLE_VERBS,
    ENRICH_SKIP_MIN_CHARS,
    GRAPH_QUERY_MAX_RESULTS,
    SCOUT_GRAPH_TOOLS,
)
from server.config.settings import AppSettings
from server.toolkit.tools.code_graph_tools import (
    CodeBlastRadiusTool,
    CodeCallersTool,
    CodeOutlineTool,
)
from server.workspace.graph_queries import CodeGraph, clear_code_graph_cache


@pytest.fixture
def ws(temp_dir):
    """Two-module workspace: alpha defined in a.py, used in b.py and c.py."""
    (temp_dir / "a.py").write_text(
        "def alpha(x):\n    return x * 2\n\ndef beta():\n    return 'unused-by-others'\n",
        encoding="utf-8",
    )
    (temp_dir / "b.py").write_text(
        "from a import alpha\n\ndef gamma():\n    return alpha(21)\n",
        encoding="utf-8",
    )
    (temp_dir / "c.py").write_text("value = alpha(3) + gamma()\n", encoding="utf-8")
    clear_code_graph_cache()
    yield temp_dir
    clear_code_graph_cache()


def test_callers_finds_usage_sites_with_lines(ws):
    graph = CodeGraph(ws)
    sites = graph.callers("alpha")
    files = {s["file"] for s in sites}
    assert {"b.py", "c.py"} <= files, sites
    assert all(s["line"] for s in sites), "usage lines must be populated"


def test_callers_unknown_symbol_is_empty(ws):
    assert CodeGraph(ws).callers("definitely_not_here") == []


def test_outline_lists_definitions(ws):
    defs = CodeGraph(ws).outline("a.py")
    names = {d["name"] for d in defs}
    assert {"alpha", "beta"} <= names


def test_outline_rejects_escape_and_missing(ws):
    assert CodeGraph(ws).outline("../outside.py") == []
    assert CodeGraph(ws).outline("missing.py") == []


def test_blast_radius_counts_caller_files(ws):
    radius = CodeGraph(ws).blast_radius("alpha")
    assert radius["caller_count"] >= 2
    assert "b.py" in radius["affected_files"]
    assert "c.py" in radius["affected_files"]


def test_top_symbols_ranks_by_reference_count(ws):
    hubs = CodeGraph(ws).top_symbols(5)
    assert hubs, "hub list must not be empty"
    top_name = hubs[0][0]
    assert top_name in ("alpha", "gamma")


def test_max_results_cap(ws):
    sites = CodeGraph(ws).callers("alpha", max_results=1)
    assert len(sites) <= GRAPH_QUERY_MAX_RESULTS


# ---- scout tools ----------------------------------------------------------


@pytest.mark.asyncio
async def test_code_callers_tool(ws):
    result = await CodeCallersTool().execute({"symbol": "alpha"}, str(ws))
    assert result.success
    assert "b.py" in result.output and "c.py" in result.output
    assert result.metadata["count"] >= 2


@pytest.mark.asyncio
async def test_code_outline_tool(ws):
    result = await CodeOutlineTool().execute({"path": "a.py"}, str(ws))
    assert result.success
    assert "alpha" in result.output


@pytest.mark.asyncio
async def test_code_blast_radius_tool(ws):
    result = await CodeBlastRadiusTool().execute({"symbol": "alpha"}, str(ws))
    assert result.success
    assert "calling file(s)" in result.output
    assert result.metadata["affected_files"]


@pytest.mark.asyncio
async def test_tools_require_symbol(ws):
    for tool in (CodeCallersTool(), CodeBlastRadiusTool()):
        result = await tool.execute({}, str(ws))
        assert result.success is False


# ---- mission brief --------------------------------------------------------


def test_mission_brief_contains_hubs_and_stats(ws):
    from server.agents.delegation.scout import build_mission_brief

    brief = build_mission_brief(str(ws))
    assert brief is not None and "Workspace:" in brief
    assert "Hub symbols" in brief
    assert "alpha" in brief


def test_mission_brief_capped(ws):
    from server.agents.delegation.scout import build_mission_brief
    from server.config.constants import EXPLORE_BRIEF_MAX_CHARS

    assert len(build_mission_brief(str(ws)) or "") <= EXPLORE_BRIEF_MAX_CHARS


# ---- enrichment gate ------------------------------------------------------


def test_enrichment_gate_rules():
    from server.toolkit.tools.explore_tool import ExploreTool

    tool = ExploreTool(weak_model="weak-x")
    # Short + vague -> enrich.
    assert tool._should_enrich("look into auth") is True
    # Detailed enough -> skip.
    long_objective = "x" * (ENRICH_SKIP_MIN_CHARS + 1)
    assert tool._should_enrich(long_objective) is False
    # Contains a deliverable verb -> already task-shaped -> skip.
    verb = ENRICH_DELIVERABLE_VERBS[0]
    assert tool._should_enrich(f"{verb} the auth flow") is False
    # No weak model configured -> never enrich.
    bare = ExploreTool()
    assert bare._should_enrich("auth") is False


# ---- retreat clause (absence is a valid report) ---------------------------


def test_scout_prompt_carries_retreat_clause(temp_dir):
    from server.agents.delegation.scout import build_scout_prompt
    from server.agents.delegation.task_envelope import AgentTask

    task = AgentTask(
        agent_id="apogee",
        capability="codebase_investigation",
        objective="find the unicorn module",
        session_id="s",
        max_context_tokens=32_000,
    )
    prompt = build_scout_prompt(task, mission_brief=None)
    assert "RETREAT CLAUSE" in prompt
    assert "Reporting absence is a SUCCESS" in prompt
    assert "distinct searches" in prompt


def test_salvage_instruction_preserves_absence_reporting():
    from server.agents.delegation.scout import SCOUT_SALVAGE_INSTRUCTION

    assert "does not exist is a valid completed report" in SCOUT_SALVAGE_INSTRUCTION


# ---- scout allow-list regression -----------------------------------------


def test_structural_tools_allowed_in_scout_mode():
    from server.agents.delegation.scout import _SCOUT_ALLOWED_TOOLS
    from server.config.constants import SCOUT_GRAPH_TOOLS

    assert set(SCOUT_GRAPH_TOOLS) <= _SCOUT_ALLOWED_TOOLS


def test_scout_mode_schemas_offered(temp_dir):
    from server.config.settings import SCOUT_MODE_CONFIG
    from server.toolkit import create_default_registry

    reg = create_default_registry(config=AppSettings(workspace_root=str(temp_dir)))
    schemas = reg.get_schemas_for_mode(
        "scout",
        allowed_mcp=SCOUT_MODE_CONFIG.allowed_mcp,
        allowed_tools=SCOUT_MODE_CONFIG.allowed_tools,
    )
    names = {s["name"] for s in schemas}
    assert set(SCOUT_GRAPH_TOOLS) <= names
