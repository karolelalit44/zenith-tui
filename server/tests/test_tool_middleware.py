from typing import Any

import pytest

from server.toolkit.base import BaseTool, ToolContext, ToolMiddleware, ToolResult
from server.toolkit.middleware import (
    LoggingMiddleware,
    PermissionMiddleware,
    SafetyCheckMiddleware,
)
from server.toolkit.registry import ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "Echoes input"
    risk_level = "safe"

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        return ToolResult(success=True, output=params.get("text", ""))

    def get_schema(self) -> dict:
        return {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}


class FailingTool(BaseTool):
    name = "failing"
    description = "Always fails"

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        raise ValueError("intentional failure")

    def get_schema(self) -> dict:
        return {"type": "object", "properties": {}}


class TestToolBase:
    def test_tool_result_success(self):
        r = ToolResult(success=True, output="ok")
        assert r.success
        assert r.output == "ok"

    def test_tool_result_failure(self):
        r = ToolResult(success=False, error="fail")
        assert not r.success
        assert r.error == "fail"

    def test_tool_context(self):
        ctx = ToolContext(request_id="req_1", workspace_root="/tmp", mode="build")
        assert ctx.request_id == "req_1"
        assert ctx.mode == "build"

    def test_echo_tool_risk_level(self):
        assert EchoTool().risk_level == "safe"


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = EchoTool()
        reg.register(tool)
        assert reg.get("echo") is tool

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register(EchoTool())
        assert "echo" in reg.list_tools()

    def test_get_schemas(self):
        reg = ToolRegistry()
        reg.register(EchoTool())
        schemas = reg.get_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "echo"

    @pytest.mark.asyncio
    async def test_execute_tool(self):
        reg = ToolRegistry()
        reg.register(EchoTool())
        result = await reg.execute("echo", {"text": "hello"}, "/tmp")
        assert result.success
        assert result.output == "hello"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        reg = ToolRegistry()
        result = await reg.execute("nonexistent", {}, "/tmp")
        assert not result.success
        assert "Unknown tool" in result.error

    @pytest.mark.asyncio
    async def test_execute_failing_tool(self):
        reg = ToolRegistry()
        reg.register(FailingTool())
        result = await reg.execute("failing", {}, "/tmp")
        assert not result.success
        assert "intentional failure" in result.error


class TestMiddlewareChain:
    @pytest.mark.asyncio
    async def test_before_execute_short_circuit(self):
        class BlockMiddleware(ToolMiddleware):
            async def before_execute(self, name, params, ctx):
                return ToolResult(success=False, error="blocked")

        reg = ToolRegistry()
        reg.register(EchoTool())
        reg.register_middleware(BlockMiddleware())
        result = await reg.execute("echo", {"text": "hi"}, "/tmp")
        assert not result.success
        assert "blocked" in result.error

    @pytest.mark.asyncio
    async def test_after_execute_transform(self):
        class UpperMiddleware(ToolMiddleware):
            async def before_execute(self, name, params, ctx):
                return True

            async def after_execute(self, name, params, result, ctx):
                result.output = result.output.upper()
                return result

        reg = ToolRegistry()
        reg.register(EchoTool())
        reg.register_middleware(UpperMiddleware())
        result = await reg.execute("echo", {"text": "hello"}, "/tmp")
        assert result.output == "HELLO"

    @pytest.mark.asyncio
    async def test_on_error_recovery(self):
        class RecoverMiddleware(ToolMiddleware):
            async def before_execute(self, name, params, ctx):
                return True

            async def on_error(self, name, params, error, ctx):
                return ToolResult(success=True, output="recovered")

        reg = ToolRegistry()
        reg.register(FailingTool())
        reg.register_middleware(RecoverMiddleware())
        result = await reg.execute("failing", {}, "/tmp")
        assert result.success
        assert result.output == "recovered"

    @pytest.mark.asyncio
    async def test_middleware_order(self):
        order = []

        class MW1(ToolMiddleware):
            async def before_execute(self, name, params, ctx):
                order.append("mw1_before")
                return True

            async def after_execute(self, name, params, result, ctx):
                order.append("mw1_after")
                return result

        class MW2(ToolMiddleware):
            async def before_execute(self, name, params, ctx):
                order.append("mw2_before")
                return True

            async def after_execute(self, name, params, result, ctx):
                order.append("mw2_after")
                return result

        reg = ToolRegistry()
        reg.register(EchoTool())
        reg.register_middleware(MW1())
        reg.register_middleware(MW2())
        await reg.execute("echo", {"text": "x"}, "/tmp")
        assert order == ["mw1_before", "mw2_before", "mw1_after", "mw2_after"]


class TestSafetyCheckMiddleware:
    @pytest.mark.asyncio
    async def test_blocks_banned_command(self):
        mw = SafetyCheckMiddleware()
        ctx = ToolContext(request_id="r1", mode="build")
        result = await mw.before_execute("bash", {"command": "sudo rm -rf /"}, ctx)
        assert isinstance(result, ToolResult)
        assert not result.success
        assert "blocked" in result.error.lower() or "safety" in result.error.lower()

    @pytest.mark.asyncio
    async def test_allows_safe_command(self):
        mw = SafetyCheckMiddleware()
        ctx = ToolContext(request_id="r1", mode="build")
        result = await mw.before_execute("bash", {"command": "echo hello"}, ctx)
        assert result is True

    @pytest.mark.asyncio
    async def test_ignores_non_bash(self):
        mw = SafetyCheckMiddleware()
        ctx = ToolContext(request_id="r1", mode="build")
        result = await mw.before_execute("file_read", {"path": "/etc/passwd"}, ctx)
        assert result is True


class TestPermissionMiddleware:
    @pytest.mark.asyncio
    async def test_no_callback_allows(self):
        mw = PermissionMiddleware()
        ctx = ToolContext(request_id="r1", mode="build")
        result = await mw.before_execute("bash", {"command": "ls"}, ctx)
        assert result is True

    @pytest.mark.asyncio
    async def test_callback_approves(self):
        async def approve(name, params, ctx):
            return True

        mw = PermissionMiddleware(check=approve)
        ctx = ToolContext(request_id="r1", mode="build")
        result = await mw.before_execute("bash", {"command": "ls"}, ctx)
        assert result is True

    @pytest.mark.asyncio
    async def test_callback_denies(self):
        async def deny(name, params, ctx):
            return ToolResult(success=False, error="denied")

        mw = PermissionMiddleware(check=deny)
        ctx = ToolContext(request_id="r1", mode="build")
        result = await mw.before_execute("bash", {"command": "ls"}, ctx)
        assert isinstance(result, ToolResult)
        assert not result.success


class TestLoggingMiddleware:
    @pytest.mark.asyncio
    async def test_before_execute_sets_start_time(self):
        mw = LoggingMiddleware()
        ctx = ToolContext(request_id="r1", mode="build")
        result = await mw.before_execute("echo", {"text": "hi"}, ctx)
        assert result is True
        assert "_start_time" in ctx.metadata

    @pytest.mark.asyncio
    async def test_after_execute_returns_result(self):
        mw = LoggingMiddleware()
        ctx = ToolContext(request_id="r1", mode="build")
        await mw.before_execute("echo", {"text": "hi"}, ctx)
        original = ToolResult(success=True, output="ok")
        result = await mw.after_execute("echo", {"text": "hi"}, original, ctx)
        assert result is original
