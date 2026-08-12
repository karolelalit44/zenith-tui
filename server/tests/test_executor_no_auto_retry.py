import pytest

from server.config.constants import FILE_EXISTS_ERROR_MARKER
from server.toolkit.executor import execute_tool
from server.toolkit.registry import ToolRegistry
from server.toolkit.tools.file_write import FileWriteTool


class TestFileWriteNoAutoRetry:
    """Regression for the removed executor auto-retry (executor.py).

    Writing to a path that already exists must surface a real failure to the
    model instead of being silently retried with overwrite=True.
    """

    @pytest.mark.asyncio
    async def test_first_write_succeeds(self, tmp_path):
        reg = ToolRegistry()
        reg.register(FileWriteTool())
        result, _ = await execute_tool(
            reg,
            "file_write",
            {"path": "a.txt", "content": "hello"},
            str(tmp_path),
            "build",
        )
        assert result.success
        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello"

    @pytest.mark.asyncio
    async def test_repeat_write_fails_without_masking(self, tmp_path):
        reg = ToolRegistry()
        reg.register(FileWriteTool())
        target = tmp_path / "a.txt"
        target.write_text("existing", encoding="utf-8")
        result, _ = await execute_tool(
            reg,
            "file_write",
            {"path": "a.txt", "content": "hello"},
            str(tmp_path),
            "build",
        )
        assert not result.success
        assert FILE_EXISTS_ERROR_MARKER in result.error
        assert target.read_text(encoding="utf-8") == "existing"

    @pytest.mark.asyncio
    async def test_explicit_overwrite_still_succeeds(self, tmp_path):
        reg = ToolRegistry()
        reg.register(FileWriteTool())
        target = tmp_path / "a.txt"
        target.write_text("existing", encoding="utf-8")
        result, _ = await execute_tool(
            reg,
            "file_write",
            {"path": "a.txt", "content": "hello", "overwrite": True},
            str(tmp_path),
            "build",
        )
        assert result.success
        assert target.read_text(encoding="utf-8") == "hello"
