import asyncio
import platform
import sys
import time
from pathlib import Path

import pytest

from server.config.constants import (
    BASH_TOOL_DESCRIPTION_UNIX,
    BASH_TOOL_DESCRIPTION_WINDOWS,
)
from server.toolkit import create_default_registry
from server.toolkit.auto_lint import detect_linter, run_lint
from server.toolkit.base import ToolResult
from server.toolkit.registry import ToolRegistry
from server.toolkit.tools.background import get_background_manager
from server.toolkit.tools.bash import BashTool
from server.toolkit.tools.file_delete import FileDeleteTool
from server.toolkit.tools.file_edit import FileEditTool
from server.toolkit.tools.file_read import FileReadTool
from server.toolkit.tools.file_write import FileWriteTool
from server.toolkit.tools.glob import GlobTool
from server.toolkit.tools.grep import GrepTool
from server.toolkit.tools.webfetch import WebfetchTool


def test_file_write_documents_parent_dir_creation():
    tool = FileWriteTool()
    assert "automatically" in tool.description
    schema = tool.get_schema()
    assert "automatically" in schema["properties"]["path"]["description"]


def test_bash_description_states_working_directory():
    tool = BashTool()
    if platform.system() == "Windows":
        assert "Set-Location" in tool.description
    else:
        assert "cd" in tool.description
    assert "workspace" in tool.description


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


class TestAutoLint:
    def test_detect_linter_by_extension(self):
        assert detect_linter("a.py") is not None
        assert detect_linter("a.tsx") is not None
        assert detect_linter("a.unknown") is None

    @pytest.mark.asyncio
    async def test_run_lint_fix_removes_unused_import(self, temp_dir):
        target = temp_dir / "fixme.py"
        target.write_text("import math\nprint('hi')\n", encoding="utf-8")
        result = await run_lint(str(target), str(temp_dir), fix=True)
        assert result is not None
        assert result.success, f"auto-fix should clean the file, got: {result}"
        assert "import math" not in target.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_run_lint_unfixable_error_still_reported(self, temp_dir):
        target = temp_dir / "broken.py"
        target.write_text("def foo():\n    return missing_symbol\n", encoding="utf-8")
        result = await run_lint(str(target), str(temp_dir), fix=True)
        assert result is not None
        assert not result.success, "an unfixable lint error must still be reported"
        assert "missing_symbol" in result.output

    @pytest.mark.asyncio
    async def test_run_lint_without_fix_keeps_file(self, temp_dir):
        target = temp_dir / "keep.py"
        target.write_text("import math\nprint('hi')\n", encoding="utf-8")
        result = await run_lint(str(target), str(temp_dir), fix=False)
        assert result is not None
        assert not result.success
        assert "import math" in target.read_text(encoding="utf-8")


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


BUILD_ONLY_TOOLS = [
    "bash",
    "agent",
    "todo",
    "job_kill",
    "file_write",
    "file_edit",
    "file_delete",
    "multi_edit",
    "lsp_rename",
]


class TestModeGating:
    def test_plan_mode_excludes_all_mutating_tools(self):
        reg = create_default_registry()
        plan_names = set(reg.list_tools_for_mode("plan"))
        for name in BUILD_ONLY_TOOLS:
            assert name not in plan_names, f"{name} leaked into plan mode"

    def test_build_mode_includes_mutating_tools(self):
        reg = create_default_registry()
        build_names = set(reg.list_tools_for_mode("build"))
        for name in BUILD_ONLY_TOOLS:
            assert name in build_names, f"{name} missing from build mode"

    @pytest.mark.asyncio
    async def test_plan_mode_execution_rejects_leaked_tools(self):
        reg = create_default_registry()
        for name in ("bash", "agent", "todo", "job_kill"):
            result = await reg.execute(name, {"command": "echo hi"}, ".", mode="plan")
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

    @pytest.mark.asyncio
    async def test_success_surfaces_stderr(self, temp_dir):
        tool = BashTool()
        script = "import sys; sys.stderr.write('boom-on-stderr\\n')"
        script_path = Path(temp_dir) / "_stderr_probe.py"
        script_path.write_text(script, encoding="utf-8")
        result = await tool.execute(
            {"command": f"{_python_cmd()} \"{script_path}\""}, str(temp_dir)
        )
        assert result.success
        assert result.metadata.get("exit_code") == 0
        assert "boom-on-stderr" in result.output
        assert result.metadata.get("stderr_len", 0) > 0

    def test_schema(self):
        tool = BashTool()
        schema = tool.get_schema()
        assert "command" in schema["properties"]
        assert "command" in schema["required"]

    def test_description_mentions_powershell_on_windows(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        tool = BashTool()
        assert tool.description == BASH_TOOL_DESCRIPTION_WINDOWS
        assert "PowerShell" in tool.description
        assert "Unix" in tool.description

    def test_description_mentions_shell_on_unix(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        tool = BashTool()
        assert tool.description == BASH_TOOL_DESCRIPTION_UNIX
        assert "shell" in tool.description.lower()
        assert "mkdir -p" in tool.description

    def test_schema_command_param_is_os_aware(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        schema = BashTool().get_schema()
        assert "PowerShell" in schema["properties"]["command"]["description"]

        monkeypatch.setattr(platform, "system", lambda: "Linux")
        schema = BashTool().get_schema()
        assert "PowerShell" not in schema["properties"]["command"]["description"]
        assert "Shell command" in schema["properties"]["command"]["description"]


def _python_cmd() -> str:
    if " " in sys.executable:
        return "python"
    return sys.executable


def _slow_command(temp_dir, marker: str) -> str:
    script = temp_dir / f"slow_{marker}.py"
    script.write_text(
        f"import time\ntime.sleep(1.5)\nprint('{marker}')\n",
        encoding="utf-8",
    )
    return f"{_python_cmd()} {script}"


async def _wait_for_job(manager, job_id: str, marker: str, timeout: float = 10.0) -> str | None:
    deadline = time.monotonic() + timeout
    output: str | None = None
    while time.monotonic() < deadline:
        output = manager.get_output(job_id)
        if output and "Completed" in output and marker in output:
            return output
        await asyncio.sleep(0.1)
    return output


class TestBackgroundJobs:
    @pytest.mark.asyncio
    async def test_direct_background_job_starts_and_completes(self, temp_dir):
        tool = BashTool()
        result = await tool.execute(
            {"command": _slow_command(temp_dir, "bg-done"), "run_in_background": True},
            str(temp_dir),
        )
        assert result.success
        assert result.metadata.get("background") is True
        job_id = result.metadata.get("job_id")
        assert job_id
        output = await _wait_for_job(get_background_manager(), job_id, "bg-done")
        assert output is not None, "background job never completed"
        assert "bg-done" in output

    @pytest.mark.asyncio
    async def test_auto_backgrounded_command_adopts_running_process(self, temp_dir):
        tool = BashTool(auto_background_after=1)
        start = time.monotonic()
        result = await tool.execute(
            {"command": _slow_command(temp_dir, "auto-bg")}, str(temp_dir)
        )
        assert result.metadata.get("background") is True, "should auto-background"
        assert result.success
        job_id = result.metadata.get("job_id")
        assert job_id
        elapsed = time.monotonic() - start
        assert elapsed < 5, f"auto-background returned too slowly: {elapsed:.1f}s"
        output = await _wait_for_job(get_background_manager(), job_id, "auto-bg")
        assert output is not None, "adopted background job never completed"
        assert "auto-bg" in output


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
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_delete_directory_tree_recursively(self, temp_dir):
        sub = temp_dir / "subdir"
        sub.mkdir()
        (sub / "a.py").write_text("x")
        (sub / "nested").mkdir()
        (sub / "nested" / "b.py").write_text("y")
        tool = FileDeleteTool()
        result = await tool.execute({"path": "subdir"}, str(temp_dir))
        assert result.success
        assert not sub.exists(), "directory tree must be removed"
        assert result.metadata.get("directory") is True
        assert result.metadata.get("entries", 0) == 3


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

    @pytest.mark.asyncio
    async def test_glob_caps_overflowing_results(self, temp_dir, monkeypatch):
        import server.toolkit.tools.glob as glob_mod

        monkeypatch.setattr(glob_mod, "GLOB_MAX_RESULTS", 2)
        for i in range(5):
            (temp_dir / f"f{i}.py").write_text("")
        tool = GlobTool()
        result = await tool.execute({"pattern": "*.py"}, str(temp_dir))
        assert result.success
        assert result.metadata["count"] == 5, "count reports the true total"
        assert len(result.metadata["files"]) == 2, "returned list must be capped"
        assert "more matches omitted" in result.output


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
        assert "websearch" in tools
        assert "job_output" in tools
        assert "job_kill" in tools
        assert "list_dir" in tools
        assert "multi_edit" in tools
        assert "todo" in tools
        assert "lsp_diagnostics" in tools
        assert "lsp_definition" in tools
        assert "lsp_rename" in tools
        assert "agent" in tools
        assert "discover_capabilities" in tools
        assert "get_tool_definition" in tools
        assert len(tools) == 20
