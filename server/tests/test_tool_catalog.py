from typing import Any

import pytest

from server.toolkit import (
    create_default_registry,
    estimate_tool_schema_tokens,
    measure_registry_schema_tokens,
    validate_registry,
)
from server.toolkit.base import BaseTool, ToolResult
from server.toolkit.catalog import build_catalog, build_inventory
from server.toolkit.registry import ToolRegistry


def make_tool(*, name: str, schema: dict | None = None, **attrs):
    class TestTool(BaseTool):
        async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
            return ToolResult(success=True, output="ok")

        def get_schema(self) -> dict:
            return schema or {"type": "object", "properties": {}, "required": []}

    TestTool.name = name
    for key, value in {
        "description": "Test tool",
        "capability_id": "file_read",
        "read_only": True,
        "permission_scope": "read",
        "requires_mode": None,
        **attrs,
    }.items():
        setattr(TestTool, key, value)
    return TestTool()


EXPECTED_TOOLS = {
    "bash",
    "code_blast_radius",
    "code_callers",
    "code_outline",
    "discover_capabilities",
    "file_delete",
    "file_edit",
    "file_read",
    "file_write",
    "get_tool_definition",
    "glob",
    "grep",
    "job_kill",
    "job_output",
    "list_dir",
    "lsp_definition",
    "lsp_diagnostics",
    "lsp_rename",
    "multi_edit",
    "todo",
    "webfetch",
    "websearch",
}


class TestCapabilityCatalog:
    def test_known_capabilities(self):
        catalog = build_catalog()
        for capability_id in (
            "workspace_discovery",
            "file_read",
            "content_search",
            "file_write",
            "file_edit",
            "file_delete",
            "command_execution",
            "background_jobs",
            "web_fetch",
            "lsp_analysis",
            "lsp_refactoring",
            "task_tracking",
            "sub_agent",
            "mcp_tool",
            "tool_discovery",
        ):
            assert catalog.get(capability_id) is not None

    def test_descriptor_shape(self):
        catalog = build_catalog()
        descriptor = catalog.get("command_execution")
        assert descriptor is not None
        assert descriptor.name
        assert descriptor.short_description
        assert descriptor.domains
        assert descriptor.search_terms
        assert not descriptor.read_only


class TestToolInventory:
    def test_inventory_covers_all_tools(self):
        registry = create_default_registry()
        inventory = build_inventory(registry)
        names = {entry.name for entry in inventory}
        assert names == EXPECTED_TOOLS
        assert len(inventory) == len(EXPECTED_TOOLS)

    def test_every_tool_maps_to_known_capability(self):
        catalog = build_catalog()
        inventory = build_inventory(create_default_registry())
        for entry in inventory:
            assert catalog.get(entry.capability_id) is not None, entry.name

    def test_read_only_metadata(self):
        inventory = {e.name: e for e in build_inventory(create_default_registry())}
        assert inventory["file_read"].read_only is True
        assert inventory["glob"].read_only is True
        assert inventory["grep"].read_only is True
        assert inventory["bash"].read_only is False
        assert inventory["file_write"].read_only is False
        assert inventory["file_delete"].read_only is False

    def test_mode_declarations(self):
        inventory = {e.name: e for e in build_inventory(create_default_registry())}
        assert inventory["file_read"].modes == []
        assert inventory["file_write"].modes == []
        assert inventory["file_edit"].modes == []
        assert inventory["bash"].modes == ["build"]

    def test_permission_and_concurrency(self):
        inventory = {e.name: e for e in build_inventory(create_default_registry())}
        assert inventory["bash"].permission_scope == "command"
        assert inventory["bash"].concurrency_group == "shell"
        assert inventory["file_write"].concurrency_group == "workspace_mutation"
        assert inventory["webfetch"].permission_scope == "network"
        # WP5 D7: the legacy write-capable "agent" tool is no longer on the
        # default registry surface; subagent-class permission lives on explore.
        assert "agent" not in inventory

    def test_baseline_schema_tokens(self):
        baseline = measure_registry_schema_tokens(create_default_registry())
        assert baseline["tool_count"] == len(EXPECTED_TOOLS)
        assert baseline["total_tokens"] > 0
        assert set(baseline["tools"]) == EXPECTED_TOOLS

    def test_estimate_single_schema(self):
        tokens = estimate_tool_schema_tokens(
            {"type": "object", "properties": {"path": {"type": "string"}}},
            "Read a file",
        )
        assert tokens > 0


class TestRegistryValidation:
    def test_default_registry_valid(self):
        assert validate_registry(create_default_registry()) == []

    def test_duplicate_name_detected(self):
        registry = ToolRegistry()
        registry.register(make_tool(name="dup"))
        with pytest.raises(ValueError, match="Duplicate tool name"):
            registry.register(make_tool(name="dup"))

    def test_empty_description_detected(self):
        registry = ToolRegistry()
        registry.register(make_tool(name="t1", description=""))
        errors = validate_registry(registry)
        assert any("description is empty" in e for e in errors)

    def test_oversized_description_detected(self):
        registry = ToolRegistry()
        registry.register(make_tool(name="t1", description="x" * 500))
        errors = validate_registry(registry)
        assert any("description exceeds" in e for e in errors)

    def test_invalid_mode_declaration_detected(self):
        registry = ToolRegistry()
        registry.register(make_tool(name="t1", requires_mode="hacked"))
        errors = validate_registry(registry)
        assert any("invalid mode declaration" in e for e in errors)

    def test_unknown_capability_detected(self):
        registry = ToolRegistry()
        registry.register(make_tool(name="t1", capability_id="no_such_capability"))
        errors = validate_registry(registry)
        assert any("unknown capability_id" in e for e in errors)

    def test_invalid_permission_scope_detected(self):
        registry = ToolRegistry()
        registry.register(make_tool(name="t1", permission_scope="evil"))
        errors = validate_registry(registry)
        assert any("invalid permission_scope" in e for e in errors)

    def test_read_only_permission_mismatch_detected(self):
        registry = ToolRegistry()
        registry.register(make_tool(name="t1", read_only=False, permission_scope="read"))
        errors = validate_registry(registry)
        assert any("read_only=False but permission_scope" in e for e in errors)

    def test_invalid_schema_type_detected(self):
        registry = ToolRegistry()
        registry.register(make_tool(name="t1", schema={"type": "string"}))
        errors = validate_registry(registry)
        assert any("must be 'object'" in e for e in errors)

    def test_invalid_schema_required_detected(self):
        registry = ToolRegistry()
        registry.register(
            make_tool(
                name="t1",
                schema={"type": "object", "properties": {}, "required": ["missing"]},
            )
        )
        errors = validate_registry(registry)
        assert any("references undefined properties" in e for e in errors)
