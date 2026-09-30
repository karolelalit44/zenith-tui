"""Phase 1 contracts: the model can verify, recover, and never stalls.

Three guarantees are pinned here.

* A completed mutation reports a *receipt* — where it landed, what it changed,
  and which rung of the match ladder fired. Previously a mutation reported only
  "Edited <path>", which is indistinguishable from a no-op and forces a
  re-read to confirm anything.
* A failed lookup carries its own recovery. "File not found: x" with no
  alternatives turns one typo into a retry loop.
* A failed operation is classified. A raw errno string names a platform
  symptom and offers no recovery, so the only available move is to repeat the
  identical call and get the identical string.
"""

from __future__ import annotations

import errno
from pathlib import Path

import pytest

from server.toolkit.base import ToolResult
from server.toolkit.errors import (
    CONFLICT,
    ENCODING,
    IO_ERROR,
    IS_DIRECTORY,
    LOCKED,
    NOT_FOUND,
    NO_SPACE,
    PERMISSION,
    READ_ONLY,
    classify,
    conflict_error,
    describe,
)
from server.toolkit.path_validator import not_found_error, suggest_alternatives
from server.toolkit.tools.apply_patch import ApplyPatchTool
from server.toolkit.tools.file_delete import FileDeleteTool
from server.toolkit.tools.file_edit import FileEditTool
from server.toolkit.tools.file_read import FileReadTool
from server.toolkit.tools.file_write import FileWriteTool


# --------------------------------------------------------------------------
# P1.1  Edit receipts
# --------------------------------------------------------------------------


class TestEditReceipt:
    @pytest.mark.asyncio
    async def test_receipt_locates_the_change(self, temp_dir: Path):
        path = temp_dir / "a.py"
        path.write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")

        result = await FileEditTool().execute(
            {"path": "a.py", "old_content": "three", "new_content": "THREE\nthree-b"},
            str(temp_dir),
        )

        assert result.success
        lines = result.output.splitlines()
        assert lines[0] == "Edited a.py"
        assert "line 3 replaced" in lines[1]
        assert "(+2 -1 lines)" in lines[1]
        assert "match=exact" in lines[1]
        # 5 original lines, one of which became two.
        assert "6 line(s)" in lines[2]

    @pytest.mark.asyncio
    async def test_receipt_reports_a_loosened_match_loudly(self, temp_dir: Path):
        path = temp_dir / "a.py"
        path.write_text("def f():\n    return 1\n", encoding="utf-8")

        # The needle is a whole line carrying trailing whitespace the file does
        # not, so the exact rung fails and the rstrip rung is what actually lands.
        result = await FileEditTool().execute(
            {"path": "a.py", "old_content": "    return 1  ", "new_content": "    return 2"},
            str(temp_dir),
        )

        assert result.success
        assert result.metadata["match"] == "trimmed"
        assert "match=trimmed (loosened match)" in result.output

    @pytest.mark.asyncio
    async def test_receipt_covers_a_multi_line_region(self, temp_dir: Path):
        path = temp_dir / "a.py"
        path.write_text("1\n2\n3\n4\n5\n", encoding="utf-8")
        result = await FileEditTool().execute(
            {"path": "a.py", "old_content": "2\n3\n4", "new_content": "X"}, str(temp_dir)
        )
        assert result.success
        assert "lines 2-4 replaced" in result.output
        assert "(+1 -3 lines)" in result.output

    @pytest.mark.asyncio
    async def test_receipt_counts_every_replacement(self, temp_dir: Path):
        path = temp_dir / "a.py"
        path.write_text("x = 1\nx = 1\n", encoding="utf-8")
        result = await FileEditTool().execute(
            {"path": "a.py", "old_content": "x = 1", "new_content": "x = 2", "replaceAll": True},
            str(temp_dir),
        )
        assert result.success
        assert "2 separate regions" in result.output
        assert "(+2 -2 lines)" in result.output

    @pytest.mark.asyncio
    async def test_receipt_reports_the_true_resulting_size(self, temp_dir: Path):
        path = temp_dir / "a.py"
        path.write_text("alpha\nbeta\n", encoding="utf-8")
        result = await FileEditTool().execute(
            {"path": "a.py", "old_content": "beta", "new_content": "gamma\ndelta\nepsilon"},
            str(temp_dir),
        )
        assert result.success
        assert path.read_text(encoding="utf-8") == "alpha\ngamma\ndelta\nepsilon\n"
        assert "4 line(s)" in result.output
        assert f"{len(path.read_bytes())} byte(s)" in result.output


# --------------------------------------------------------------------------
# P1.2  Patch receipts
# --------------------------------------------------------------------------


PATCH_MIXED = """*** Begin Patch
*** Add File: created.txt
+hello
+world
*** Update File: edited.txt
@@
-alpha
+ALPHA
*** Delete File: gone.txt
*** End Patch
"""


class TestPatchReceipt:
    @pytest.mark.asyncio
    async def test_receipt_classifies_each_operation(self, temp_dir: Path):
        (temp_dir / "edited.txt").write_text("alpha\n", encoding="utf-8")
        (temp_dir / "gone.txt").write_text("x\n", encoding="utf-8")

        result = await ApplyPatchTool().execute({"patch": PATCH_MIXED}, str(temp_dir))

        assert result.success
        assert "Applied patch (3 file(s))" in result.output
        assert "A created.txt (+2 -0)" in result.output
        assert "M edited.txt (+1 -1)" in result.output
        assert "D gone.txt (+0 -1)" in result.output

    @pytest.mark.asyncio
    async def test_receipt_names_a_rename_as_a_rename(self, temp_dir: Path):
        (temp_dir / "old.txt").write_text("keep\n", encoding="utf-8")
        patch = (
            "*** Begin Patch\n"
            "*** Update File: old.txt\n"
            "*** Move to: new.txt\n"
            "@@\n"
            " keep\n"
            "*** End Patch\n"
        )
        result = await ApplyPatchTool().execute({"patch": patch}, str(temp_dir))
        assert result.success
        assert "R old.txt -> new.txt" in result.output
        assert not (temp_dir / "old.txt").exists()
        assert (temp_dir / "new.txt").exists()

    @pytest.mark.asyncio
    async def test_totals_are_exposed_as_metadata(self, temp_dir: Path):
        (temp_dir / "edited.txt").write_text("alpha\n", encoding="utf-8")
        (temp_dir / "gone.txt").write_text("x\n", encoding="utf-8")
        result = await ApplyPatchTool().execute({"patch": PATCH_MIXED}, str(temp_dir))
        assert result.metadata["added"] == 3
        assert result.metadata["removed"] == 2
        assert result.metadata["count"] == 3


# --------------------------------------------------------------------------
# P1.3  Not-found carries its own recovery
# --------------------------------------------------------------------------


class TestNotFoundSuggestions:
    @pytest.mark.asyncio
    async def test_near_miss_filename_is_suggested(self, temp_dir: Path):
        for name in ("file_read.py", "file_write.py", "registry.py"):
            (temp_dir / name).write_text("x", encoding="utf-8")

        result = await FileReadTool().execute({"path": "file_reed.py"}, str(temp_dir))
        assert result.success is False
        assert "File not found: file_reed.py" in result.error
        assert "Did you mean one of these?" in result.error
        assert "file_read.py" in result.error

    @pytest.mark.asyncio
    async def test_wrong_directory_is_suggested(self, temp_dir: Path):
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "mod.py").write_text("x", encoding="utf-8")
        (temp_dir / "tests").mkdir()

        result = await FileReadTool().execute({"path": "srz/mod.py"}, str(temp_dir))
        assert result.success is False
        assert "src/" in result.error

    @pytest.mark.asyncio
    async def test_no_suggestions_when_nothing_is_close(self, temp_dir: Path):
        (temp_dir / "alpha.py").write_text("x", encoding="utf-8")
        result = await FileReadTool().execute({"path": "zzzzzzzz.py"}, str(temp_dir))
        assert result.success is False
        assert "Did you mean" not in result.error

    @pytest.mark.asyncio
    async def test_message_stays_clean_when_nothing_exists_at_all(self, temp_dir: Path):
        result = await FileReadTool().execute({"path": "ghost.py"}, str(temp_dir))
        assert result.success is False
        assert result.error == "File not found: ghost.py"

    def test_suggestions_are_capped_and_bounded(self, temp_dir: Path):
        for i in range(50):
            (temp_dir / f"module_{i}.py").write_text("x", encoding="utf-8")
        assert len(suggest_alternatives("module_1x.py", str(temp_dir))) <= 3

    @pytest.mark.asyncio
    async def test_every_file_tool_uses_the_same_message(self, temp_dir: Path):
        read = await FileReadTool().execute({"path": "nope.py"}, str(temp_dir))
        edit = await FileEditTool().execute(
            {"path": "nope.py", "old_content": "a", "new_content": "b"}, str(temp_dir)
        )
        delete = await FileDeleteTool().execute({"path": "nope.py"}, str(temp_dir))
        for result in (read, edit, delete):
            assert result.error.startswith("File not found: nope.py"), result.error

    def test_helper_is_safe_on_a_path_with_no_parent(self, temp_dir: Path):
        (temp_dir / "a.py").write_text("x", encoding="utf-8")
        assert not_found_error("", str(temp_dir)) == "File not found: "


# --------------------------------------------------------------------------
# P1.4  Failures are classified, never raw errno strings
# --------------------------------------------------------------------------


class TestFailureClassification:
    def test_categories_are_stable(self):
        assert classify(UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")) == ENCODING
        assert classify(IsADirectoryError(21, "Is a directory")) == IS_DIRECTORY
        assert classify(FileNotFoundError(2, "No such file")) == NOT_FOUND
        assert classify(PermissionError(13, "Permission denied")) == PERMISSION
        assert classify(OSError("unmapped")) == IO_ERROR

    def test_posix_errnos_map(self):
        for code, expected in (
            (errno.ENOENT, NOT_FOUND),
            (errno.EACCES, PERMISSION),
            (errno.EROFS, READ_ONLY),
            (errno.EISDIR, IS_DIRECTORY),
            (errno.ENOSPC, NO_SPACE),
        ):
            assert classify(OSError(code, os_strerror(code))) == expected

    def test_windows_errnos_map(self):
        for win, expected in (
            (5, PERMISSION),
            (32, LOCKED),
            (19, READ_ONLY),
            (112, NO_SPACE),
        ):
            exc = OSError(13, "x")
            exc.winerror = win
            assert classify(exc) == expected

    @pytest.mark.parametrize(
        "exc,expected",
        [
            (PermissionError(13, "denied"), PERMISSION),
            (FileNotFoundError(2, "gone"), NOT_FOUND),
            (IsADirectoryError(21, "isdir"), IS_DIRECTORY),
        ],
    )
    def test_message_names_the_category_in_plain_language(self, exc, expected):
        message = describe(exc, action="write", path="a/b.py")
        assert "a/b.py" in message
        assert "Failed to write" in message
        # No raw platform vocabulary may reach the model.
        assert "Errno" not in message
        assert "WinError" not in message
        assert expected != IO_ERROR or "filesystem operation failed" in message

    def test_non_retryable_failures_say_so(self):
        permission = describe(PermissionError(13, "x"), action="write", path="a.py")
        assert "will not succeed on retry" in permission
        readonly = describe(OSError(errno.EROFS, "ro"), action="write", path="a.py")
        assert "cannot help" in readonly

    def test_locked_failure_names_the_cause(self):
        # errno 13 + winerror 32 is how Windows reports a file open elsewhere.
        exc = OSError(13, "x")
        exc.winerror = 32
        assert classify(exc) == LOCKED
        message = describe(exc, action="write", path="a.py")
        assert "locked by another process" in message
        assert "release" in message
        # A lock is transient; the model must not be told to change ownership.
        assert "another user" not in message

    def test_every_category_has_a_recovery_instruction(self):
        for category in (
            NOT_FOUND, PERMISSION, LOCKED, READ_ONLY, IS_DIRECTORY,
            NO_SPACE, ENCODING, CONFLICT, IO_ERROR,
        ):
            exc = {
                NOT_FOUND: FileNotFoundError(2, "x"),
                PERMISSION: PermissionError(13, "x"),
                LOCKED: PermissionError(13, "x"),
                READ_ONLY: OSError(errno.EROFS, "ro"),
                IS_DIRECTORY: IsADirectoryError(21, "x"),
                NO_SPACE: OSError(errno.ENOSPC, "full"),
                ENCODING: UnicodeDecodeError("utf-8", b"\xff", 0, 1, "b"),
                CONFLICT: OSError(0, "x"),
                IO_ERROR: OSError(0, "x"),
            }[category]
            message = describe(exc, action="write", path="a.py")
            assert message.rstrip().endswith(".") and len(message) > 60, category

    def test_conflict_message_is_specific(self):
        message = conflict_error("a.py")
        assert "changed on disk" in message
        assert "Re-read" in message

    @pytest.mark.asyncio
    async def test_directory_write_says_so_instead_of_advising_overwrite(self, temp_dir: Path):
        (temp_dir / "adir").mkdir()
        result = await FileWriteTool().execute(
            {"path": "adir", "content": "x"}, str(temp_dir)
        )
        assert result.success is False
        assert "Path is a directory" in result.error
        # Previously this returned "Use overwrite: true", which cannot work.
        assert "overwrite" not in result.error

    @pytest.mark.asyncio
    async def test_tool_failure_no_longer_leaks_a_raw_errno(self, temp_dir: Path, monkeypatch):
        def boom(self, *args, **kwargs):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(Path, "write_bytes", boom)
        result = await FileWriteTool().execute(
            {"path": "a.py", "content": "x", "overwrite": True}, str(temp_dir)
        )

        assert result.success is False
        assert "Errno" not in result.error
        assert "WinError" not in result.error
        assert "Failed to write" in result.error
        assert "will not succeed on retry" in result.error


def os_strerror(code: int) -> str:
    import os as _os

    return _os.strerror(code)


def test_result_type_is_unchanged():
    # Guards the ToolResult contract the tools above rely on.
    assert ToolResult(success=True, output="x").success is True
