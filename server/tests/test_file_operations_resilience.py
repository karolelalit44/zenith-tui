import pytest
from pathlib import Path

from server.toolkit.tools.apply_patch import ApplyPatchTool
from server.toolkit.tools.file_delete import FileDeleteTool
from server.toolkit.tools.file_edit import FileEditTool
from server.toolkit.tools.file_read import FileReadTool
from server.toolkit.tools.file_write import FileWriteTool
from server.toolkit.tools.glob import GlobTool
from server.toolkit.tools.grep import GrepTool
from server.agents.session_workspace import get_cached_read, record_read


@pytest.fixture
def temp_workspace(tmp_path):
    # Setup standard workspace with a .zenithignore
    ignore_file = tmp_path / ".zenithignore"
    ignore_file.write_text("ignored_folder/\npackage-lock.json\n*.secret\n", encoding="utf-8")
    return tmp_path


class TestSearchResilience:
    @pytest.mark.asyncio
    async def test_grep_literal_with_special_characters(self, temp_workspace):
        target = temp_workspace / "code.py"
        target.write_text("result = re.compile(r'(?<=abc)[def]')\n", encoding="utf-8")

        tool = GrepTool()
        # Invalid regex syntax without literal=True fails gracefully
        res_invalid = await tool.execute(
            {"path": ".", "pattern": "(?<=abc)[def", "literal": False},
            str(temp_workspace),
        )
        assert not res_invalid.success
        assert "literal" in res_invalid.error.lower() or "regex" in res_invalid.error.lower()

        # With literal=True, it succeeds
        res_literal = await tool.execute(
            {"path": ".", "pattern": "(?<=abc)[def]", "literal": True},
            str(temp_workspace),
        )
        assert res_literal.success
        assert "code.py:1" in res_literal.output

    @pytest.mark.asyncio
    async def test_grep_skips_binary_files(self, temp_workspace):
        bin_file = temp_workspace / "data.bin"
        bin_file.write_bytes(b"\x00\x01\x02TARGET\x00\xff")

        tool = GrepTool()
        result = await tool.execute(
            {"path": ".", "pattern": "TARGET", "literal": True},
            str(temp_workspace),
        )
        assert result.success
        assert "data.bin" not in result.output

    @pytest.mark.asyncio
    async def test_glob_in_subpath(self, temp_workspace):
        sub = temp_workspace / "sub" / "dir"
        sub.mkdir(parents=True)
        (sub / "test_a.txt").write_text("a")
        (sub / "test_b.txt").write_text("b")

        tool = GlobTool()
        result = await tool.execute(
            {"path": "sub/dir", "pattern": "*.txt"},
            str(temp_workspace),
        )
        assert result.success
        assert "sub/dir/test_a.txt" in result.output
        assert "sub/dir/test_b.txt" in result.output


class TestReadResilience:
    @pytest.mark.asyncio
    async def test_read_ignores_zenithignore_for_direct_file(self, temp_workspace):
        target = temp_workspace / "package-lock.json"
        target.write_text('{"name": "test-pkg", "version": "1.0.0"}', encoding="utf-8")

        tool = FileReadTool()
        result = await tool.execute({"path": "package-lock.json"}, str(temp_workspace))
        assert result.success
        assert "test-pkg" in result.output

    @pytest.mark.asyncio
    async def test_read_long_lines_truncated(self, temp_workspace):
        long_line = "A" * 3000
        target = temp_workspace / "minified.js"
        target.write_text(long_line + "\nsecond line", encoding="utf-8")

        tool = FileReadTool()
        result = await tool.execute({"path": "minified.js"}, str(temp_workspace))
        assert result.success
        assert "... (line truncated to 2000 chars)" in result.output
        assert "second line" in result.output

    @pytest.mark.asyncio
    async def test_read_binary_file_refused(self, temp_workspace):
        target = temp_workspace / "program.exe"
        target.write_bytes(b"MZ\x90\x00\x03\x00\x00\x00")

        tool = FileReadTool()
        result = await tool.execute({"path": "program.exe"}, str(temp_workspace))
        assert not result.success
        assert "binary" in result.error.lower()

    @pytest.mark.asyncio
    async def test_read_image_file_returns_descriptor(self, temp_workspace):
        target = temp_workspace / "logo.png"
        target.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        tool = FileReadTool()
        result = await tool.execute({"path": "logo.png"}, str(temp_workspace))
        assert result.success
        assert "[Image file:" in result.output


class TestWriteAndRewriteResilience:
    @pytest.mark.asyncio
    async def test_write_creates_nested_missing_directories(self, temp_workspace):
        tool = FileWriteTool()
        result = await tool.execute(
            {"path": "a/b/c/d/deep.txt", "content": "deep content"},
            str(temp_workspace),
        )
        assert result.success
        created = temp_workspace / "a/b/c/d/deep.txt"
        assert created.exists()
        assert created.read_text(encoding="utf-8") == "deep content"

    @pytest.mark.asyncio
    async def test_write_preserves_crlf_and_bom_on_overwrite(self, temp_workspace):
        target = temp_workspace / "crlf_bom.txt"
        target.write_bytes(b"\xef\xbb\xbfLine1\r\nLine2\r\n")

        tool = FileWriteTool()
        result = await tool.execute(
            {"path": "crlf_bom.txt", "content": "Updated1\nUpdated2", "overwrite": True},
            str(temp_workspace),
        )
        assert result.success
        raw = target.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")
        assert b"\r\n" in raw
        assert raw == b"\xef\xbb\xbfUpdated1\r\nUpdated2"

    @pytest.mark.asyncio
    async def test_write_to_ignored_path_allowed(self, temp_workspace):
        tool = FileWriteTool()
        result = await tool.execute(
            {"path": "package-lock.json", "content": '{"version": "2.0.0"}'},
            str(temp_workspace),
        )
        assert result.success
        assert (temp_workspace / "package-lock.json").read_text() == '{"version": "2.0.0"}'


class TestEditResilience:
    @pytest.mark.asyncio
    async def test_edit_preserves_crlf_and_bom(self, temp_workspace):
        target = temp_workspace / "source.txt"
        target.write_bytes(b"\xef\xbb\xbfHeader\r\nTarget Line\r\nFooter\r\n")

        tool = FileEditTool()
        result = await tool.execute(
            {
                "path": "source.txt",
                "old_content": "Target Line\n",
                "new_content": "Replacement Line\n",
            },
            str(temp_workspace),
        )
        assert result.success
        raw = target.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")
        assert b"\r\n" in raw
        assert b"Replacement Line" in raw

    @pytest.mark.asyncio
    async def test_edit_replace_all(self, temp_workspace):
        target = temp_workspace / "multi.txt"
        target.write_text("foo = 1\nbar = foo + foo\n", encoding="utf-8")

        tool = FileEditTool()
        # Without replaceAll -> ambiguous error
        res_ambiguous = await tool.execute(
            {"path": "multi.txt", "old_content": "foo", "new_content": "baz"},
            str(temp_workspace),
        )
        assert not res_ambiguous.success
        assert "Ambiguous" in res_ambiguous.error

        # With replaceAll -> replaces all 3
        res_all = await tool.execute(
            {"path": "multi.txt", "old_content": "foo", "new_content": "baz", "replaceAll": True},
            str(temp_workspace),
        )
        assert res_all.success
        assert target.read_text(encoding="utf-8") == "baz = 1\nbar = baz + baz\n"

    @pytest.mark.asyncio
    async def test_edit_trailing_whitespace_trimmed_fallback(self, temp_workspace):
        # File has trailing spaces on lines
        target = temp_workspace / "trailing.txt"
        target.write_text("function test() {   \n    return 42;  \n}\n", encoding="utf-8")

        tool = FileEditTool()
        # LLM provides lines without trailing spaces
        result = await tool.execute(
            {
                "path": "trailing.txt",
                "old_content": "function test() {\n    return 42;\n}",
                "new_content": "function test() {\n    return 100;\n}",
            },
            str(temp_workspace),
        )
        assert result.success
        assert result.metadata.get("match") == "trimmed"
        assert "return 100;" in target.read_text(encoding="utf-8")


class TestApplyPatchResilience:
    @pytest.mark.asyncio
    async def test_apply_patch_multi_file(self, temp_workspace):
        (temp_workspace / "existing.py").write_text("def hello():\n    print('hello')\n", encoding="utf-8")
        (temp_workspace / "obsolete.py").write_text("old file\n", encoding="utf-8")

        patch = (
            "*** Begin Patch\n"
            "*** Add File: new_module.py\n"
            "+def added():\n"
            "+    return True\n"
            "*** Update File: existing.py\n"
            "@@ def hello():\n"
            " def hello():\n"
            "-    print('hello')\n"
            "+    print('hello world')\n"
            "*** Delete File: obsolete.py\n"
            "*** End Patch"
        )

        tool = ApplyPatchTool()
        result = await tool.execute({"patch": patch}, str(temp_workspace))
        assert result.success
        assert (temp_workspace / "new_module.py").read_text(encoding="utf-8") == "def added():\n    return True"
        assert "hello world" in (temp_workspace / "existing.py").read_text(encoding="utf-8")
        assert not (temp_workspace / "obsolete.py").exists()

    @pytest.mark.asyncio
    async def test_apply_patch_atomic_failure_reverts_all(self, temp_workspace):
        (temp_workspace / "intact.py").write_text("def intact(): pass\n", encoding="utf-8")

        # Patch has one good add and one impossible update hunk
        patch = (
            "*** Begin Patch\n"
            "*** Add File: should_not_exist.py\n"
            "+content\n"
            "*** Update File: intact.py\n"
            "@@ nonexistent context\n"
            "-impossible\n"
            "+replacement\n"
            "*** End Patch"
        )

        tool = ApplyPatchTool()
        result = await tool.execute({"patch": patch}, str(temp_workspace))
        assert not result.success
        assert "Patch hunk failed" in result.error
        # The add was NEVER performed because of atomic dry-run validation
        assert not (temp_workspace / "should_not_exist.py").exists()
        assert (temp_workspace / "intact.py").read_text(encoding="utf-8") == "def intact(): pass\n"

    @pytest.mark.asyncio
    async def test_apply_patch_move_file(self, temp_workspace):
        (temp_workspace / "src_old.txt").write_text("move me\n", encoding="utf-8")

        patch = (
            "*** Begin Patch\n"
            "*** Update File: src_old.txt\n"
            "*** Move to: dest_new.txt\n"
            "@@ move me\n"
            "-move me\n"
            "+moved successfully\n"
            "*** End Patch"
        )

        tool = ApplyPatchTool()
        result = await tool.execute({"patch": patch}, str(temp_workspace))
        assert result.success
        assert not (temp_workspace / "src_old.txt").exists()
        assert (temp_workspace / "dest_new.txt").read_text(encoding="utf-8") == "moved successfully\n"
