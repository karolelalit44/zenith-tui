"""Module 03 tool_service — additive interface-lock tests.

Covers the opencode ``Tool.Def``-aligned additive surface: ``ToolDef``,
``decode_parameters`` / ``InvalidToolArgumentsError``, and the unified
``truncate_output`` service. Purely additive; none of this removes legacy
registry/router/resolver behavior (Phase 3).
"""

from __future__ import annotations

import asyncio

import pytest

from server.toolkit.base import (
    InvalidToolArgumentsError,
    ToolDef,
    ToolResult,
    decode_parameters,
    run_tool_def,
    truncate_output,
)


class TestToolDef:
    def test_plain_definition(self):
        tool = ToolDef(name="bash", description="Run a command")
        assert tool.name == "bash"
        assert tool.description == "Run a command"
        assert tool.parameters["type"] == "object"

    def test_to_schema(self):
        tool = ToolDef(
            name="file_read",
            description="Read a file",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        )
        schema = tool.to_schema()
        assert schema["name"] == "file_read"
        assert schema["parameters"]["properties"] == {"path": {"type": "string"}}

    def test_execute_hook(self):
        captured = {}

        def run(params, ctx):
            captured["params"] = params
            return "ran"

        tool = ToolDef(name="t", description="d", execute=run)
        assert tool.execute({"a": 1}, {}) == "ran"
        assert captured["params"] == {"a": 1}


class TestDecodeParameters:
    def test_required_satisfied(self):
        schema = {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }
        assert decode_parameters(schema, {"path": "/tmp"}) == {"path": "/tmp"}

    def test_missing_required_raises(self):
        schema = {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }
        with pytest.raises(InvalidToolArgumentsError):
            decode_parameters(schema, {})

    def test_disallowed_property_raises(self):
        schema = {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "additionalProperties": False,
        }
        with pytest.raises(InvalidToolArgumentsError):
            decode_parameters(schema, {"path": "/tmp", "extra": 1})

    def test_no_schema_passes_through(self):
        assert decode_parameters(None, {"anything": 1}) == {"anything": 1}


class TestTruncateOutput:
    def test_short_unchanged(self):
        text, truncated = truncate_output("short", max_chars=1000)
        assert text == "short"
        assert truncated is False

    def test_truncates_long(self):
        text, truncated = truncate_output("x" * 100, max_chars=20)
        assert truncated is True
        assert "truncated" in text
        # The cap is smaller than the marker: no payload content survives here.
        assert text.startswith("\n... [output truncated")

    def test_payload_kept_within_cap(self):
        text, truncated = truncate_output("x" * 100, max_chars=80)
        assert truncated is True
        assert "truncated" in text
        assert len(text) <= 80

    def test_default_limit_used(self):
        text, truncated = truncate_output("y" * 20000)
        assert truncated is True
        assert "truncated" in text

    def test_empty(self):
        text, truncated = truncate_output("", max_chars=10)
        assert text == ""
        assert truncated is False

    def test_none_limit_no_truncation(self):
        text, truncated = truncate_output("z" * 100, max_chars=None)
        assert truncated is False
        assert len(text) == 100


class TestRunToolDef:
    def test_invalid_args_fed_back_as_rewrite_request(self):
        async def execute(params, workspace_root):
            return ToolResult(success=True, output="")

        tool = ToolDef(
            name="write",
            description="write a file",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            execute=execute,
        )
        res = asyncio.run(run_tool_def(tool, {"content": "x"}, "/w"))
        assert res.ok is False
        assert "Missing required argument 'path'" in res.error
        assert res.output == ""

    def test_success_and_truncation(self):
        async def execute(params, workspace_root):
            return ToolResult(success=True, output="x" * 200)

        # Cap large enough to retain some payload past the marker (66 chars).
        tool = ToolDef(name="read", description="read", execute=execute)
        res = asyncio.run(run_tool_def(tool, {}, "/w", max_output_chars=100))
        assert res.ok is True
        assert res.truncated is True
        assert "truncated" in res.output
        assert len(res.output) <= 100

    def test_truncation_within_default_limit(self):
        async def execute(params, workspace_root):
            return ToolResult(success=True, output="y" * 3000)

        tool = ToolDef(name="cat", description="cat", execute=execute)
        res = asyncio.run(run_tool_def(tool, {}, "/w"))
        assert res.ok is True
        assert res.truncated is False  # 3000 chars < MAX_TOOL_OUTPUT_BASELINE

    def test_metadata_passthrough(self):
        async def execute(params, workspace_root):
            return ToolResult(success=True, output="ok", metadata={"k": 1})

        tool = ToolDef(name="x", description="x", execute=execute)
        res = asyncio.run(run_tool_def(tool, {}, "/w"))
        assert res.metadata == {"k": 1}

    def test_plain_string_return(self):
        async def execute(params, workspace_root):
            return "plain result"

        tool = ToolDef(name="y", description="y", execute=execute)
        res = asyncio.run(run_tool_def(tool, {}, "/w"))
        assert res.ok is True
        assert res.output == "plain result"
