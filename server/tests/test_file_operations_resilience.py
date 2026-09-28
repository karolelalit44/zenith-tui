from pathlib import Path

import pytest

from server.toolkit.registry import current_tool_session_id
from server.toolkit.tools.apply_patch import ApplyPatchTool
from server.toolkit.tools.file_delete import FileDeleteTool
from server.toolkit.tools.file_edit import FileEditTool
from server.toolkit.tools.file_read import FileReadTool
from server.toolkit.tools.file_write import FileWriteTool
from server.toolkit.tools.glob import GlobTool
from server.toolkit.tools.grep import GrepTool


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
    async def test_write_to_ignored_path_blocked(self, temp_workspace):
        # Ignored paths are hidden from every discovery tool, so a writer must
        # refuse rather than overwrite a vendored/generated file the model cannot
        # even see. The refusal names .zenithignore instead of claiming the file is
        # missing: a false "not found" sends the agent hunting for a file that is
        # right there on disk.
        tool = FileWriteTool()
        result = await tool.execute(
            {"path": "package-lock.json", "content": '{"version": "2.0.0"}'},
            str(temp_workspace),
        )
        assert not result.success
        assert ".zenithignore" in result.error
        assert "not found" not in result.error.lower()
        assert not (temp_workspace / "package-lock.json").exists()


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

    @pytest.mark.asyncio
    async def test_edit_does_not_rewrite_untouched_line_endings(self, temp_workspace):
        # A one-line edit must splice only the replaced range. Restyling the
        # whole file turns a targeted change into a whole-file diff and breaks
        # line-ending-sensitive tooling.
        target = temp_workspace / "mixed.txt"
        target.write_bytes(b"alpha\r\nbeta\ngamma\r\ndelta")

        tool = FileEditTool()
        result = await tool.execute(
            {"path": "mixed.txt", "old_content": "gamma", "new_content": "GAMMA"},
            str(temp_workspace),
        )
        assert result.success
        assert target.read_bytes() == b"alpha\r\nbeta\nGAMMA\r\ndelta"

    @pytest.mark.asyncio
    async def test_edit_preserves_absent_trailing_newline(self, temp_workspace):
        target = temp_workspace / "no_newline.txt"
        target.write_bytes(b"abc")

        tool = FileEditTool()
        result = await tool.execute(
            {"path": "no_newline.txt", "old_content": "c", "new_content": "C"},
            str(temp_workspace),
        )
        assert result.success
        assert target.read_bytes() == b"abC"

    @pytest.mark.asyncio
    async def test_edit_splices_mid_line_fragment(self, temp_workspace):
        target = temp_workspace / "call.txt"
        target.write_text("foo(bar, baz)\n", encoding="utf-8")

        tool = FileEditTool()
        result = await tool.execute(
            {"path": "call.txt", "old_content": "bar", "new_content": "QUX"},
            str(temp_workspace),
        )
        assert result.success
        assert target.read_text(encoding="utf-8") == "foo(QUX, baz)\n"

    @pytest.mark.asyncio
    async def test_edit_refuses_non_utf8_without_mutating(self, temp_workspace):
        # errors="replace" would silently turn every invalid byte into U+FFFD
        # and report success. Refusing is the only lossless option.
        target = temp_workspace / "latin1.py"
        original = b"x = 1  # caf\xe9\ny = 2\n"
        target.write_bytes(original)

        tool = FileEditTool()
        result = await tool.execute(
            {"path": "latin1.py", "old_content": "y = 2", "new_content": "y = 3"},
            str(temp_workspace),
        )
        assert not result.success
        assert "utf-8" in result.error.lower()
        assert target.read_bytes() == original

    @pytest.mark.asyncio
    async def test_edit_to_ignored_path_blocked(self, temp_workspace):
        ignored = temp_workspace / "ignored_folder"
        ignored.mkdir()
        target = ignored / "keep.txt"
        target.write_text("original\n", encoding="utf-8")

        tool = FileEditTool()
        result = await tool.execute(
            {
                "path": "ignored_folder/keep.txt",
                "old_content": "original",
                "new_content": "clobbered",
            },
            str(temp_workspace),
        )
        assert not result.success
        assert ".zenithignore" in result.error
        assert "not found" not in result.error.lower()
        assert target.read_text(encoding="utf-8") == "original\n"

    @pytest.mark.asyncio
    async def test_delete_to_ignored_path_blocked(self, temp_workspace):
        ignored = temp_workspace / "ignored_folder"
        ignored.mkdir()
        target = ignored / "keep.txt"
        target.write_text("original\n", encoding="utf-8")

        tool = FileDeleteTool()
        result = await tool.execute({"path": "ignored_folder/keep.txt"}, str(temp_workspace))
        assert not result.success
        assert ".zenithignore" in result.error
        assert target.exists()


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
    async def test_apply_patch_to_ignored_path_blocked(self, temp_workspace):
        ignored = temp_workspace / "ignored_folder"
        ignored.mkdir()
        target = ignored / "pkg.js"
        target.write_text("module.exports = 1\n", encoding="utf-8")

        patch = (
            "*** Begin Patch\n"
            "*** Update File: ignored_folder/pkg.js\n"
            "@@\n"
            "-module.exports = 1\n"
            "+module.exports = 2\n"
            "*** End Patch"
        )
        tool = ApplyPatchTool()
        result = await tool.execute({"patch": patch}, str(temp_workspace))
        assert not result.success
        assert ".zenithignore" in result.error
        assert target.read_text(encoding="utf-8") == "module.exports = 1\n"

    @pytest.mark.asyncio
    async def test_apply_patch_preserves_per_line_endings(self, temp_workspace):
        # A file that mixes LF and CRLF must not be restyled wholesale by a
        # one-hunk patch, including the context lines the chunk quotes.
        target = temp_workspace / "mixed.py"
        target.write_bytes(b"a\r\nb\nc\r\nd\r\n")

        patch = (
            "*** Begin Patch\n"
            "*** Update File: mixed.py\n"
            "@@\n"
            " b\n"
            "-c\n"
            "+C\n"
            "*** End Patch"
        )
        tool = ApplyPatchTool()
        result = await tool.execute({"patch": patch}, str(temp_workspace))
        assert result.success
        assert target.read_bytes() == b"a\r\nb\nC\r\nd\r\n"

    @pytest.mark.asyncio
    async def test_apply_patch_appends_with_add_only_hunk(self, temp_workspace):
        # A hunk whose lines are all "+" replaces nothing (old_lines == []) and
        # appends. This shape reaches a different branch than a replace hunk and
        # must not be reported as a failed patch.
        target = temp_workspace / "appended.py"
        target.write_text("def a():\n    pass\n", encoding="utf-8")

        patch = (
            "*** Begin Patch\n"
            "*** Update File: appended.py\n"
            "@@\n"
            "+def b():\n"
            "+    pass\n"
            "*** End Patch"
        )
        tool = ApplyPatchTool()
        result = await tool.execute({"patch": patch}, str(temp_workspace))
        assert result.success, result.error
        assert target.read_text(encoding="utf-8") == "def a():\n    pass\ndef b():\n    pass\n"

    @pytest.mark.asyncio
    async def test_apply_patch_append_only_hunk_keeps_file_terminator_style(
        self, temp_workspace
    ):
        target = temp_workspace / "crlf_append.py"
        target.write_bytes(b"a\r\nb\r\n")

        patch = (
            "*** Begin Patch\n"
            "*** Update File: crlf_append.py\n"
            "@@\n"
            "+c\n"
            "*** End Patch"
        )
        tool = ApplyPatchTool()
        result = await tool.execute({"patch": patch}, str(temp_workspace))
        assert result.success, result.error
        assert target.read_bytes() == b"a\r\nb\r\nc\r\n"

    @pytest.mark.asyncio
    async def test_apply_patch_append_only_hunk_closes_unterminated_last_line(
        self, temp_workspace
    ):
        # The last line ends at EOF with no terminator; without an explicit close
        # the first appended line is glued onto it, corrupting both. The appended
        # group keeps the file's no-trailing-newline state.
        target = temp_workspace / "no_newline_append.py"
        target.write_bytes(b"def a():\n    pass")

        patch = (
            "*** Begin Patch\n"
            "*** Update File: no_newline_append.py\n"
            "@@\n"
            "+def b():\n"
            "+    pass\n"
            "*** End Patch"
        )
        tool = ApplyPatchTool()
        result = await tool.execute({"patch": patch}, str(temp_workspace))
        assert result.success, result.error
        assert target.read_bytes() == b"def a():\n    pass\ndef b():\n    pass"

    @pytest.mark.asyncio
    async def test_apply_patch_refuses_non_utf8_without_mutating(self, temp_workspace):
        target = temp_workspace / "latin1.py"
        original = b"p = 1  # caf\xe9\nq = 2\n"
        target.write_bytes(original)

        patch = (
            "*** Begin Patch\n"
            "*** Update File: latin1.py\n"
            "@@\n"
            "-p = 1  # caf\xe9\n"
            "+P = 1\n"
            "*** End Patch"
        )
        tool = ApplyPatchTool()
        result = await tool.execute({"patch": patch}, str(temp_workspace))
        assert not result.success
        assert "utf-8" in result.error.lower()
        assert target.read_bytes() == original

    @pytest.mark.asyncio
    async def test_apply_patch_rolls_back_when_later_op_fails(
        self, temp_workspace, monkeypatch
    ):
        # Reporting failure while leaving earlier hunks on disk is worse than
        # failing: the model retries and then fails on context mismatch.
        first = temp_workspace / "first.py"
        first.write_text("A\n", encoding="utf-8")
        second = temp_workspace / "second.py"
        second.write_text("B\n", encoding="utf-8")
        created = temp_workspace / "created.py"

        patch = (
            "*** Begin Patch\n"
            "*** Add File: created.py\n"
            "+new\n"
            "*** Update File: first.py\n"
            "@@\n"
            "-A\n"
            "+A2\n"
            "*** Update File: second.py\n"
            "@@\n"
            "-B\n"
            "+B2\n"
            "*** End Patch"
        )

        real_write_bytes = Path.write_bytes

        def failing_write(self, data):
            if self.name == "second.py":
                raise OSError("simulated write failure")
            return real_write_bytes(self, data)

        monkeypatch.setattr(Path, "write_bytes", failing_write)
        tool = ApplyPatchTool()
        result = await tool.execute({"patch": patch}, str(temp_workspace))

        assert not result.success
        assert "restored" in result.error.lower()
        assert first.read_text(encoding="utf-8") == "A\n"
        assert second.read_text(encoding="utf-8") == "B\n"
        assert not created.exists()

    @pytest.mark.asyncio
    async def test_apply_patch_read_cache_invalidated_without_session(
        self, temp_workspace
    ):
        # Read slices are cached per absolute path. Invalidation must not be
        # gated on the session contextvar, or a delegated/background write
        # leaves the primary session serving pre-write content.
        target = temp_workspace / "cached.py"
        target.write_text("value = 1\n", encoding="utf-8")

        session = "cache-invalidation-session"
        current_tool_session_id.set(session)
        try:
            read_tool = FileReadTool()
            first = await read_tool.execute({"path": "cached.py"}, str(temp_workspace))
            assert first.success
            assert "value = 1" in first.output

            # Write from outside any session context.
            current_tool_session_id.set(None)
            write_tool = FileWriteTool()
            written = await write_tool.execute(
                {"path": "cached.py", "content": "value = 2\n", "overwrite": True},
                str(temp_workspace),
            )
            assert written.success

            current_tool_session_id.set(session)
            second = await read_tool.execute({"path": "cached.py"}, str(temp_workspace))
            assert second.success
            assert "value = 2" in second.output
        finally:
            current_tool_session_id.set(None)

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


class TestContextLifecycleAndDriftResilience:
    @pytest.mark.asyncio
    async def test_write_then_read_then_edit_lifecycle(self, temp_workspace):
        """Verify the exact lifecycle: create file -> read ground truth -> edit portion -> verify fresh content."""
        token = current_tool_session_id.set("lifecycle-session-1")
        try:
            write_tool = FileWriteTool()
            read_tool = FileReadTool()
            edit_tool = FileEditTool()

            # 1. Create file with initial content
            init_code = (
                "def calculate_tax(subtotal: float) -> float:\n"
                "    rate = 0.05\n"
                "    return subtotal * rate\n"
            )
            write_res = await write_tool.execute(
                {"path": "pricing.py", "content": init_code},
                str(temp_workspace),
            )
            assert write_res.success
            assert (temp_workspace / "pricing.py").read_text(encoding="utf-8") == init_code

            # 2. Read file to confirm ground truth and line numbers
            read_res1 = await read_tool.execute({"path": "pricing.py"}, str(temp_workspace))
            assert read_res1.success
            assert "1: def calculate_tax" in read_res1.output
            assert "2:     rate = 0.05" in read_res1.output
            assert "3:     return subtotal * rate" in read_res1.output

            # 3. Edit a portion of the file (update tax rate)
            edit_res = await edit_tool.execute(
                {
                    "path": "pricing.py",
                    "old_content": "    rate = 0.05\n    return subtotal * rate",
                    "new_content": "    rate = 0.08\n    return round(subtotal * rate, 2)",
                },
                str(temp_workspace),
            )
            assert edit_res.success
            assert edit_res.metadata.get("changes") == 1

            # 4. Subsequent read MUST return the newly edited code, not stale cache
            read_res2 = await read_tool.execute({"path": "pricing.py"}, str(temp_workspace))
            assert read_res2.success
            assert "rate = 0.08" in read_res2.output
            assert "rate = 0.05" not in read_res2.output

        finally:
            current_tool_session_id.reset(token)

    @pytest.mark.asyncio
    async def test_full_rewrite_overwrites_existing_file(self, temp_workspace):
        """Verify rewriting full content of an existing file with overwrite=True."""
        token = current_tool_session_id.set("lifecycle-session-2")
        try:
            write_tool = FileWriteTool()
            read_tool = FileReadTool()

            # Step 1: Initial file
            await write_tool.execute(
                {"path": "config.json", "content": '{"version": 1}'},
                str(temp_workspace),
            )

            # Read step
            read1 = await read_tool.execute({"path": "config.json"}, str(temp_workspace))
            assert '{"version": 1}' in read1.output

            # Step 2: Full rewrite with new content
            new_config = '{\n  "version": 2,\n  "features": ["auth", "billing"]\n}'
            rewrite_res = await write_tool.execute(
                {"path": "config.json", "content": new_config, "overwrite": True},
                str(temp_workspace),
            )
            assert rewrite_res.success
            assert rewrite_res.metadata.get("overwritten") is True
            assert (temp_workspace / "config.json").read_text(encoding="utf-8") == new_config

            # Step 3: Verify read returns new content immediately
            read2 = await read_tool.execute({"path": "config.json"}, str(temp_workspace))
            assert '"version": 2' in read2.output
            assert '"version": 1' not in read2.output
        finally:
            current_tool_session_id.reset(token)

    def test_heavy_operations_compaction_preserves_file_read(self):
        """Under heavy operations, compaction digests verbose tool outputs but protects file_read content."""
        from server.agents.compaction import prune_inflight_messages

        # Simulate a long, heavy turn with 12 tool calls:
        # file_read followed by 10 verbose bash/search outputs
        messages = [
            {
                "role": "user",
                "content": "[Tool: file_read | Status: SUCCESS]\n1: def critical_logic():\n2:     return 42\n",
                "digest": "Read critical_logic.py (2 lines)",
            }
        ]
        for i in range(10):
            messages.append(
                {
                    "role": "user",
                    "content": "[Tool: bash | Status: SUCCESS]\n" + ("test output line\n" * 50),
                    "digest": f"Ran test #{i} (50 lines)",
                }
            )

        # Prune with keep_latest_tools=3
        pruned, _stats = prune_inflight_messages(messages, keep_latest_tools=3)

        # The file_read message at index 0 must NOT be collapsed to a hollow digest
        file_read_msg = pruned[0]["content"]
        assert "def critical_logic():" in file_read_msg
        assert "return 42" in file_read_msg

        # Older bash tool messages should be reduced to digests to prevent context overflow
        assert pruned[1]["content"] == "Ran test #0 (50 lines)"

