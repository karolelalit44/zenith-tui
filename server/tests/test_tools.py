import pytest

from server.toolkit import create_default_registry
from server.toolkit.base import ToolResult
from server.toolkit.registry import ToolRegistry
from server.toolkit.tools.bash import BashTool
from server.toolkit.tools.file_delete import FileDeleteTool
from server.toolkit.tools.file_edit import FileEditTool
from server.toolkit.tools.file_read import FileReadTool
from server.toolkit.tools.file_write import FileWriteTool
from server.toolkit.tools.glob import GlobTool
from server.toolkit.tools.grep import GrepTool
from server.toolkit.tools.webfetch import WebfetchTool


class TestToolResult:
    def test_success_result(self):
        result = ToolResult(success=True, output="ok")
        assert result.success
        assert result.output == "ok"
        assert result.error == ""
        assert result.metadata == {}

    def test_failure_result(self):
        result = ToolResult(success=False, error="failed")
        assert not result.success
        assert result.error == "failed"

    def test_result_with_metadata(self):
        result = ToolResult(success=True, output="ok", metadata={"count": 5})
        assert result.metadata["count"] == 5


class TestToolRegistry:
    def test_empty_registry(self):
        reg = ToolRegistry()
        assert reg.list_tools() == []

    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = BashTool()
        reg.register(tool)
        assert reg.get("bash") is tool

    def test_get_nonexistent(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register(BashTool())
        reg.register(GlobTool())
        names = reg.list_tools()
        assert "bash" in names
        assert "glob" in names

    def test_get_schemas(self):
        reg = ToolRegistry()
        reg.register(GlobTool())
        schemas = reg.get_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "glob"

    def test_get_schemas_for_mode_plan(self):
        reg = ToolRegistry()
        reg.register(FileReadTool())
        reg.register(FileWriteTool())
        schemas = reg.get_schemas_for_mode("plan")
        names = [s["name"] for s in schemas]
        assert "file_read" in names
        assert "file_write" not in names

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        reg = ToolRegistry()
        result = await reg.execute("nonexistent", {}, ".")
        assert not result.success
        assert "Unknown tool" in result.error

    @pytest.mark.asyncio
    async def test_execute_mode_mismatch(self):
        reg = ToolRegistry()
        reg.register(FileWriteTool())
        result = await reg.execute("file_write", {"path": "x", "content": "y"}, ".", mode="plan")
        assert not result.success
        assert "not available" in result.error


class TestBashTool:
    @pytest.mark.asyncio
    async def test_echo(self, temp_dir):
        tool = BashTool()
        result = await tool.execute({"command": "echo hello"}, str(temp_dir))
        assert result.success
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_empty_command(self, temp_dir):
        tool = BashTool()
        result = await tool.execute({"command": ""}, str(temp_dir))
        assert not result.success
        assert "No command" in result.error

    @pytest.mark.asyncio
    async def test_failing_command(self, temp_dir):
        tool = BashTool()
        result = await tool.execute({"command": "exit 1"}, str(temp_dir))
        assert not result.success
        assert result.metadata.get("exit_code") == 1

    def test_schema(self):
        tool = BashTool()
        schema = tool.get_schema()
        assert "command" in schema["properties"]
        assert "command" in schema["required"]


class TestFileReadTool:
    @pytest.mark.asyncio
    async def test_read_file(self, temp_dir):
        (temp_dir / "test.txt").write_text("line1\nline2\nline3")
        tool = FileReadTool()
        result = await tool.execute({"path": "test.txt"}, str(temp_dir))
        assert result.success
        assert "line1" in result.output
        assert "1:" in result.output

    @pytest.mark.asyncio
    async def test_read_with_offset(self, temp_dir):
        (temp_dir / "test.txt").write_text("line1\nline2\nline3")
        tool = FileReadTool()
        result = await tool.execute({"path": "test.txt", "offset": 1, "limit": 1}, str(temp_dir))
        assert result.success
        assert "line2" in result.output

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, temp_dir):
        tool = FileReadTool()
        result = await tool.execute({"path": "nope.txt"}, str(temp_dir))
        assert not result.success
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_read_directory(self, temp_dir):
        tool = FileReadTool()
        result = await tool.execute({"path": "."}, str(temp_dir))
        assert not result.success
        assert "directory" in result.error


class TestFileWriteTool:
    @pytest.mark.asyncio
    async def test_write_file(self, temp_dir):
        tool = FileWriteTool()
        result = await tool.execute({"path": "new.txt", "content": "hello"}, str(temp_dir))
        assert result.success
        assert (temp_dir / "new.txt").read_text() == "hello"

    @pytest.mark.asyncio
    async def test_write_existing_file(self, temp_dir):
        (temp_dir / "existing.txt").write_text("old")
        tool = FileWriteTool()
        result = await tool.execute({"path": "existing.txt", "content": "new"}, str(temp_dir))
        assert not result.success
        assert "already exists" in result.error

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, temp_dir):
        tool = FileWriteTool()
        result = await tool.execute(
            {"path": "sub/dir/file.txt", "content": "nested"}, str(temp_dir)
        )
        assert result.success
        assert (temp_dir / "sub/dir/file.txt").read_text() == "nested"


class TestFileEditTool:
    @pytest.mark.asyncio
    async def test_edit_file(self, temp_dir):
        (temp_dir / "edit.txt").write_text("hello world")
        tool = FileEditTool()
        result = await tool.execute(
            {"path": "edit.txt", "old_content": "world", "new_content": "there"}, str(temp_dir)
        )
        assert result.success
        assert (temp_dir / "edit.txt").read_text() == "hello there"

    @pytest.mark.asyncio
    async def test_edit_content_not_found(self, temp_dir):
        (temp_dir / "edit.txt").write_text("hello world")
        tool = FileEditTool()
        result = await tool.execute(
            {"path": "edit.txt", "old_content": "xyz", "new_content": "abc"}, str(temp_dir)
        )
        assert not result.success
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_edit_ambiguous_match(self, temp_dir):
        (temp_dir / "edit.txt").write_text("aaa bbb aaa")
        tool = FileEditTool()
        result = await tool.execute(
            {"path": "edit.txt", "old_content": "aaa", "new_content": "ccc"}, str(temp_dir)
        )
        assert not result.success
        assert "Ambiguous" in result.error

    @pytest.mark.asyncio
    async def test_edit_nonexistent_file(self, temp_dir):
        tool = FileEditTool()
        result = await tool.execute(
            {"path": "nope.txt", "old_content": "a", "new_content": "b"}, str(temp_dir)
        )
        assert not result.success
        assert "not found" in result.error


class TestFileDeleteTool:
    @pytest.mark.asyncio
    async def test_delete_file(self, temp_dir):
        (temp_dir / "del.txt").write_text("delete me")
        tool = FileDeleteTool()
        result = await tool.execute({"path": "del.txt"}, str(temp_dir))
        assert result.success
        assert not (temp_dir / "del.txt").exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, temp_dir):
        tool = FileDeleteTool()
        result = await tool.execute({"path": "nope.txt"}, str(temp_dir))
        assert not result.success
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_delete_directory_fails(self, temp_dir):
        (temp_dir / "subdir").mkdir()
        tool = FileDeleteTool()
        result = await tool.execute({"path": "subdir"}, str(temp_dir))
        assert not result.success
        assert "directory" in result.error


class TestGlobTool:
    @pytest.mark.asyncio
    async def test_glob_matches(self, temp_dir):
        (temp_dir / "a.py").write_text("")
        (temp_dir / "b.py").write_text("")
        (temp_dir / "c.txt").write_text("")
        tool = GlobTool()
        result = await tool.execute({"pattern": "*.py"}, str(temp_dir))
        assert result.success
        assert result.metadata["count"] == 2

    @pytest.mark.asyncio
    async def test_glob_no_matches(self, temp_dir):
        tool = GlobTool()
        result = await tool.execute({"pattern": "*.xyz"}, str(temp_dir))
        assert result.success
        assert result.metadata["count"] == 0

    @pytest.mark.asyncio
    async def test_glob_recursive(self, temp_dir):
        (temp_dir / "sub").mkdir()
        (temp_dir / "sub" / "deep.py").write_text("")
        (temp_dir / "top.py").write_text("")
        tool = GlobTool()
        result = await tool.execute({"pattern": "**/*.py"}, str(temp_dir))
        assert result.success
        assert result.metadata["count"] == 2


class TestGrepTool:
    @pytest.mark.asyncio
    async def test_grep_finds_match(self, temp_dir):
        (temp_dir / "code.py").write_text("def hello():\n    pass\ndef world():\n    pass")
        tool = GrepTool()
        result = await tool.execute({"pattern": "def \\w+"}, str(temp_dir))
        assert result.success
        assert result.metadata["count"] == 2

    @pytest.mark.asyncio
    async def test_grep_no_matches(self, temp_dir):
        (temp_dir / "code.py").write_text("hello world")
        tool = GrepTool()
        result = await tool.execute({"pattern": "xyz"}, str(temp_dir))
        assert result.success
        assert result.metadata["count"] == 0

    @pytest.mark.asyncio
    async def test_grep_with_include(self, temp_dir):
        (temp_dir / "a.py").write_text("def hello(): pass")
        (temp_dir / "b.js").write_text("function hello() {}")
        tool = GrepTool()
        result = await tool.execute({"pattern": "hello", "include": "*.py"}, str(temp_dir))
        assert result.success
        assert result.metadata["count"] == 1

    @pytest.mark.asyncio
    async def test_grep_invalid_regex(self, temp_dir):
        tool = GrepTool()
        result = await tool.execute({"pattern": "[invalid"}, str(temp_dir))
        assert not result.success
        assert "Invalid regex" in result.error


class TestWebfetchTool:
    @pytest.mark.asyncio
    async def test_empty_url(self, temp_dir):
        tool = WebfetchTool()
        result = await tool.execute({"url": ""}, str(temp_dir))
        assert not result.success
        assert "No URL" in result.error


class TestDefaultRegistry:
    def test_create_default_registry(self):
        reg = create_default_registry()
        tools = reg.list_tools()
        assert "bash" in tools
        assert "file_read" in tools
        assert "file_write" in tools
        assert "file_edit" in tools
        assert "file_delete" in tools
        assert "glob" in tools
        assert "grep" in tools
        assert "webfetch" in tools
        assert "job_output" in tools
        assert "job_kill" in tools
        assert "multi_edit" in tools
        assert "question" in tools
        assert "todo" in tools
        assert "lsp_diagnostics" in tools
        assert "lsp_definition" in tools
        assert "lsp_rename" in tools
        assert "agent" in tools
        assert len(tools) == 17
