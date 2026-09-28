from __future__ import annotations

import pytest

from server.config.constants import (
    BUILD_MODE,
    DISCOVER_CAPABILITIES_TOOL,
    GET_TOOL_DEFINITION_TOOL,
    MAX_ACTIVE_TOOLS_PER_TURN,
    PLAN_MODE,
    RISK_SAFE,
)
from server.config.settings import CORE_BUILD_TOOLS, CORE_PLAN_TOOLS
from server.toolkit import (
    SchemaResolver,
    build_mode_tool_seed,
    create_default_registry,
)


class TestDiscoveryTools:
    def test_registered_in_default_registry(self):
        registry = create_default_registry()
        for name in (DISCOVER_CAPABILITIES_TOOL, GET_TOOL_DEFINITION_TOOL):
            tool = registry.get(name)
            assert tool is not None, name
            assert tool.read_only is True
            assert tool.capability_id == "tool_discovery"
            assert tool.risk_level == RISK_SAFE

    def test_available_in_both_modes(self):
        registry = create_default_registry()
        for mode in (BUILD_MODE, PLAN_MODE):
            names = registry.list_tools_for_mode(mode)
            assert DISCOVER_CAPABILITIES_TOOL in names
            assert GET_TOOL_DEFINITION_TOOL in names

    def test_compact_schemas(self):
        registry = create_default_registry()
        discover = registry.get(DISCOVER_CAPABILITIES_TOOL)
        get_definition = registry.get(GET_TOOL_DEFINITION_TOOL)
        schema = discover.get_schema()
        assert schema["type"] == "object"
        assert schema["properties"].get("query", {}).get("type") == "string"
        assert schema.get("required", []) == []
        props = get_definition.get_schema()["properties"]
        assert "tool_name" in props

    def test_build_seed_ships_web_tools_and_deferred_tools_still_escalate(self):
        """T1: web schemas are core build tools now (web research is first-class),
        while heavier deferred tools stay reachable via on-demand promotion."""
        assert "websearch" in CORE_BUILD_TOOLS
        assert "webfetch" in CORE_BUILD_TOOLS
        registry = create_default_registry()
        resolver = SchemaResolver(registry, seed=build_mode_tool_seed(CORE_BUILD_TOOLS))
        assert "websearch" in resolver.active_names()
        # On-demand promotion still works for non-seed tools.
        assert resolver.request_tool("file_delete") is True
        assert "file_delete" in resolver.active_names()

    @pytest.mark.asyncio
    async def test_discover_lists_capabilities(self):
        registry = create_default_registry()
        tool = registry.get(DISCOVER_CAPABILITIES_TOOL)
        result = await tool.execute({}, ".")
        assert result.success
        assert "workspace_discovery" in result.output
        assert "file_read" in result.output
        assert "get_tool_definition" in result.output

    @pytest.mark.asyncio
    async def test_get_tool_definition_returns_full_schema(self):
        registry = create_default_registry()
        tool = registry.get(GET_TOOL_DEFINITION_TOOL)
        result = await tool.execute({"tool_name": "file_edit"}, ".")
        assert result.success
        assert '"name": "file_edit"' in result.output
        assert '"parameters"' in result.output
        assert '"risk_level"' in result.output
        assert '"read_only"' in result.output

    @pytest.mark.asyncio
    async def test_get_tool_definition_unknown_tool(self):
        registry = create_default_registry()
        tool = registry.get(GET_TOOL_DEFINITION_TOOL)
        result = await tool.execute({"tool_name": "does_not_exist"}, ".")
        assert not result.success
        assert "Unknown tool" in result.error

    @pytest.mark.asyncio
    async def test_get_tool_definition_missing_name(self):
        registry = create_default_registry()
        tool = registry.get(GET_TOOL_DEFINITION_TOOL)
        result = await tool.execute({}, ".")
        assert not result.success
        assert "No tool_name" in result.error


class TestSchemaResolver:
    def test_seed_contains_core_plus_discovery(self):
        seed = build_mode_tool_seed(CORE_BUILD_TOOLS)
        assert set(seed) == set(CORE_BUILD_TOOLS) | {
            DISCOVER_CAPABILITIES_TOOL,
            GET_TOOL_DEFINITION_TOOL,
        }
        assert len(seed) == len(set(seed))

    def test_plan_seed(self):
        seed = build_mode_tool_seed(CORE_PLAN_TOOLS)
        assert DISCOVER_CAPABILITIES_TOOL in seed
        assert GET_TOOL_DEFINITION_TOOL in seed
        assert "file_write" in seed
        assert "bash" not in seed

    def test_active_set_bounded(self):
        registry = create_default_registry()
        resolver = SchemaResolver(registry, seed=build_mode_tool_seed(CORE_BUILD_TOOLS))
        assert len(resolver.active_names()) <= MAX_ACTIVE_TOOLS_PER_TURN
        assert DISCOVER_CAPABILITIES_TOOL in resolver.active_names()
        assert GET_TOOL_DEFINITION_TOOL in resolver.active_names()

    def test_request_tool_expands_active_set(self):
        registry = create_default_registry()
        resolver = SchemaResolver(registry, seed=[DISCOVER_CAPABILITIES_TOOL])
        assert resolver.request_tool("file_delete") is True
        assert "file_delete" in resolver.active_names()

    def test_request_unknown_tool_ignored(self):
        registry = create_default_registry()
        resolver = SchemaResolver(registry, seed=[])
        assert resolver.request_tool("no_such_tool") is False
        assert resolver.active_names() == []

    def test_schemas_respect_mode_filter(self):
        registry = create_default_registry()
        resolver = SchemaResolver(registry, seed=build_mode_tool_seed(CORE_BUILD_TOOLS))
        resolver.request_tool("file_write")
        plan_schemas = resolver.schemas(PLAN_MODE)
        plan_names = {s["name"] for s in plan_schemas}
        assert "file_write" in plan_names
        assert "file_delete" not in plan_names
        assert DISCOVER_CAPABILITIES_TOOL in plan_names

    def test_eviction_preserves_seed_and_discovery_tools(self):
        registry = create_default_registry()
        resolver = SchemaResolver(
            registry,
            seed=[DISCOVER_CAPABILITIES_TOOL, GET_TOOL_DEFINITION_TOOL, "file_read"],
            max_tools=3,
        )
        assert resolver.request_tool("grep") is True
        names = resolver.active_names()
        assert len(names) == 3
        # Discovery and seed tools are never evicted; the escalated tool is
        # evicted because the seed already fills the cap.
        assert DISCOVER_CAPABILITIES_TOOL in names
        assert GET_TOOL_DEFINITION_TOOL in names
        assert "file_read" in names
        assert "grep" not in names

    def test_escalation_does_not_evict_core_seed_tools(self):
        """Regression: escalating on-demand tools must not drop core tools.

        The build seed fills most of the cap; previously the first escalation
        evicted file_read (the first non-discovery tool), so a later file_read
        call bounced out of the active set and had to be re-escalated.
        """
        registry = create_default_registry()
        resolver = SchemaResolver(registry, seed=build_mode_tool_seed(CORE_BUILD_TOOLS))
        # Derive the core set from the config so seed changes are tracked
        # automatically instead of a hard-coded list.
        core = set(CORE_BUILD_TOOLS)
        for name in ("file_delete", "todo", "job_kill", "websearch"):
            assert resolver.request_tool(name) is True
        active = set(resolver.active_names())
        assert len(active) <= MAX_ACTIVE_TOOLS_PER_TURN
        assert core.issubset(active), f"core seed tools evicted: {sorted(core - active)}"

    def test_batch_escalation_never_strands_a_member(self):
        """G3: a multi-call turn escalating several on-demand tools must not
        lose the first of them to FIFO eviction while the others are added."""
        registry = create_default_registry()
        resolver = SchemaResolver(
            registry,
            seed=[DISCOVER_CAPABILITIES_TOOL, GET_TOOL_DEFINITION_TOOL, "file_read"],
            max_tools=3,
        )
        # Two escalated tools plus a full seed: batch must keep both rather
        # than dropping the first as the second is admitted. The cap is a soft
        # growth bound, so a protected batch member may push total above it.
        survivors = resolver.request_tools(["grep", "list_dir"])
        assert {"grep", "list_dir"} <= set(survivors)
        active = set(resolver.active_names())
        assert {"grep", "list_dir"} <= active

    def test_batch_escalation_evicts_prior_turn_before_batch_member(self):
        """When the combined batch pushes past the cap, a tool escalated in a
        PREVIOUS turn must be evicted before any tool of the current batch."""
        registry = create_default_registry()
        resolver = SchemaResolver(
            registry,
            seed=[DISCOVER_CAPABILITIES_TOOL, GET_TOOL_DEFINITION_TOOL, "file_read"],
            max_tools=4,
        )
        # Previous turn escalated 'grep'.
        assert resolver.request_tool("grep") is True
        assert len(resolver.active_names()) == 4
        # This turn calls list_dir + glob at once -> 6 total, cap 4.
        survivors = set(resolver.request_tools(["list_dir", "glob"]))
        active = set(resolver.active_names())
        assert {"list_dir", "glob"} <= survivors
        assert {"list_dir", "glob"} <= active
        assert len(active) <= 5  # only the single non-batch escalated tool dropped
        assert "grep" not in active  # prior-turn escalation was the eviction victim

    def test_batch_escalation_ignores_unknown_names(self):
        registry = create_default_registry()
        resolver = SchemaResolver(
            registry,
            seed=[DISCOVER_CAPABILITIES_TOOL, GET_TOOL_DEFINITION_TOOL, "file_read"],
            max_tools=4,
        )
        survivors = resolver.request_tools(["no_such_tool", "file_read"])
        assert "no_such_tool" not in survivors
        assert "file_read" in survivors

    def test_schema_tokens_positive(self):
        registry = create_default_registry()
        resolver = SchemaResolver(registry, seed=build_mode_tool_seed(CORE_BUILD_TOOLS))
        tokens = resolver.schema_tokens("gpt-4o")
        assert tokens > 0
        assert tokens < sum(_single(registry, name) for name in registry.list_tools())


def _single(registry, name: str) -> int:
    from server.toolkit.schema_metrics import estimate_tool_schema_tokens

    tool = registry.get(name)
    return estimate_tool_schema_tokens(tool.get_schema(), tool.description, "gpt-4o")


class TestSchemaMinimality:
    """Task 4.2: the schema payload sent to the provider per mode is minimal
    (seed only), and on-demand escalation grows the set without exceeding the cap."""

    def _build_openai_tools(self, seed: list[str], mode: str) -> list[dict]:
        registry = create_default_registry()
        resolver = SchemaResolver(registry, seed=build_mode_tool_seed(seed))
        from server.agents.validation import schemas_to_openai_tools

        return schemas_to_openai_tools(resolver.schemas(mode))

    def test_build_mode_schema_set_matches_seed(self):
        tools = self._build_openai_tools(CORE_BUILD_TOOLS, BUILD_MODE)
        names = {t["function"]["name"] for t in tools}
        expected = set(CORE_BUILD_TOOLS) | {
            DISCOVER_CAPABILITIES_TOOL,
            GET_TOOL_DEFINITION_TOOL,
        }
        assert names == expected

    def test_plan_mode_schema_set_matches_seed(self):
        tools = self._build_openai_tools(CORE_PLAN_TOOLS, PLAN_MODE)
        names = {t["function"]["name"] for t in tools}
        expected = set(CORE_PLAN_TOOLS) | {
            DISCOVER_CAPABILITIES_TOOL,
            GET_TOOL_DEFINITION_TOOL,
        }
        assert names == expected

    def test_build_mode_excludes_non_seed_tools(self):
        tools = self._build_openai_tools(CORE_BUILD_TOOLS, BUILD_MODE)
        names = {t["function"]["name"] for t in tools}
        for name in (
            "file_delete",
            "agent",
            "job_kill",
        ):
            assert name not in names, f"{name} leaked into build-mode seed"

    def test_escalation_adds_tool_to_openai_tools(self):
        registry = create_default_registry()
        resolver = SchemaResolver(registry, seed=build_mode_tool_seed(CORE_BUILD_TOOLS))
        from server.agents.validation import schemas_to_openai_tools

        before = schemas_to_openai_tools(resolver.schemas(BUILD_MODE))
        before_names = {t["function"]["name"] for t in before}
        assert "websearch" in before_names
        assert "file_delete" not in before_names

        resolver.request_tool("file_delete")
        after = schemas_to_openai_tools(resolver.schemas(BUILD_MODE))
        after_names = {t["function"]["name"] for t in after}
        assert "file_delete" in after_names

    def test_escalation_never_exceeds_max_active_cap(self):
        registry = create_default_registry()
        resolver = SchemaResolver(registry, seed=build_mode_tool_seed(CORE_BUILD_TOOLS))
        from server.agents.validation import schemas_to_openai_tools

        all_buildable = [
            n
            for n in registry.list_tools()
            if registry.get(n)
            and not (registry.get(n).modes and BUILD_MODE not in registry.get(n).modes)
        ]
        for name in all_buildable:
            resolver.request_tool(name)
        active = resolver.active_names()
        assert len(active) <= MAX_ACTIVE_TOOLS_PER_TURN
        tools = schemas_to_openai_tools(resolver.schemas(BUILD_MODE))
        assert len(tools) <= MAX_ACTIVE_TOOLS_PER_TURN
