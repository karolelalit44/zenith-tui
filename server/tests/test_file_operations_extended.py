"""Contracts for the first-class file operations added to close coverage gaps.

Each tool here exists because an operation had no dedicated surface, so the
model reached for a shell command — which is slower, bypasses the workspace
ignore rules and the safety checks, and produces no record of what changed.
These tests pin the behaviour that makes the tool preferable to the shell
equivalent it replaces.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from server.agents.session_workspace import reset_session
from server.config.constants import EXPECTED_HASH_PARAM
from server.toolkit.journal import JOURNAL
from server.toolkit.registry import current_tool_session_id
from server.toolkit.tools.apply_patch import ApplyPatchTool
from server.toolkit.tools.file_delete import FileDeleteTool
from server.toolkit.tools.file_edit import FileEditTool
from server.toolkit.tools.file_move import FileCopyTool, FileMoveTool
from server.toolkit.tools.file_stat import FileStatTool
from server.toolkit.tools.file_write import FileWriteTool

_SESSION = "test-file-ops"


@pytest.fixture
def session_ctx():
    JOURNAL.clear(_SESSION)
    token = current_tool_session_id.set(_SESSION)
    yield _SESSION
    current_tool_session_id.reset(token)
    reset_session(_SESSION)
    JOURNAL.clear(_SESSION)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# file_stat
# --------------------------------------------------------------------------


class TestFileStat:
    @pytest.mark.asyncio
    async def test_reports_identity_without_returning_content(self, temp_dir: Path):
        path = temp_dir / "a.py"
        path.write_bytes(b"one\ntwo\nthree\n")
        result = await FileStatTool().execute({"path": "a.py"}, str(temp_dir))

        assert result.success
        assert "one" not in result.output
        assert "size: 14 byte(s)" in result.output
        assert "lines: 3" in result.output
        assert result.metadata["sha256"] == _sha(path)
        assert result.metadata["is_binary"] is False

    @pytest.mark.asyncio
    async def test_hash_can_be_skipped_for_a_cheap_check(self, temp_dir: Path):
        (temp_dir / "a.py").write_text("x\n", encoding="utf-8")
        result = await FileStatTool().execute({"path": "a.py", "hash": False}, str(temp_dir))
        assert result.success
        assert "sha256" not in result.output
        assert "sha256" not in result.metadata

    @pytest.mark.asyncio
    async def test_zero_line_file_reports_zero_not_one(self, temp_dir: Path):
        (temp_dir / "empty.py").write_text("", encoding="utf-8")
        result = await FileStatTool().execute({"path": "empty.py"}, str(temp_dir))
        assert result.metadata["lines"] == 0

    @pytest.mark.asyncio
    async def test_directory_is_reported_as_a_directory(self, temp_dir: Path):
        (temp_dir / "pkg").mkdir()
        (temp_dir / "pkg" / "a.py").write_text("x", encoding="utf-8")
        result = await FileStatTool().execute({"path": "pkg"}, str(temp_dir))
        assert result.success
        assert result.metadata["is_dir"] is True
        assert "1 immediate entry" in result.output

    @pytest.mark.asyncio
    async def test_binary_file_is_flagged_so_a_read_is_not_attempted(
        self, temp_dir: Path
    ):
        (temp_dir / "blob.bin").write_bytes(b"\x00\x01\x02\x03binary")
        result = await FileStatTool().execute({"path": "blob.bin"}, str(temp_dir))
        assert result.metadata["is_binary"] is True
        assert "file_read will refuse it" in result.output

    @pytest.mark.asyncio
    async def test_image_file_is_reported_as_image_kind(self, temp_dir: Path):
        (temp_dir / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
        result = await FileStatTool().execute({"path": "logo.png"}, str(temp_dir))
        assert result.success
        assert result.metadata["is_dir"] is False
        assert result.metadata["is_binary"] is True
        assert "logo.png (image)" in result.output

    @pytest.mark.asyncio
    async def test_line_count_is_marked_inexact_when_sampled(self, temp_dir: Path):
        # .log is excluded by the default .zenithignore, so use a text suffix
        # that is visible, and make it large enough to exceed the sample budget.
        big = temp_dir / "big.txt"
        big.write_bytes(b"line\n" * 200_000)
        result = await FileStatTool().execute({"path": "big.txt"}, str(temp_dir))
        assert result.success
        assert result.metadata["lines_exact"] is False
        assert "lower bound" in result.output

    @pytest.mark.asyncio
    async def test_suggestions_never_reveal_an_ignored_path(self, temp_dir: Path):
        # *.log is excluded by the default ignore rules, and an ignored path is
        # reported as missing everywhere so the agent cannot learn it exists.
        # A "did you mean" that offered it back would undo that.
        (temp_dir / "secret.log").write_text("x", encoding="utf-8")
        (temp_dir / "component.tsx").write_text("x", encoding="utf-8")
        result = await FileStatTool().execute({"path": "componett.log"}, str(temp_dir))
        assert result.success is False
        assert "secret.log" not in result.error
        # And no absolute path is ever echoed back.
        assert str(temp_dir) not in result.error

    @pytest.mark.asyncio
    async def test_missing_file_suggests_alternatives(self, temp_dir: Path):
        (temp_dir / "component.tsx").write_text("x", encoding="utf-8")
        result = await FileStatTool().execute({"path": "componen.tsx"}, str(temp_dir))
        assert result.success is False
        assert "component.tsx" in result.error


# --------------------------------------------------------------------------
# file_edit by line range
# --------------------------------------------------------------------------


class TestLineRangeEdit:
    @pytest.mark.asyncio
    async def test_replaces_an_exact_line_range(self, temp_dir: Path):
        path = temp_dir / "a.py"
        path.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
        result = await FileEditTool().execute(
            {"path": "a.py", "start_line": 2, "end_line": 3, "new_content": "TWO-THREE"},
            str(temp_dir),
        )
        assert result.success
        assert path.read_text(encoding="utf-8") == "one\nTWO-THREE\nfour\n"
        assert "lines 2-3 replaced" in result.output

    @pytest.mark.asyncio
    async def test_single_line_needs_no_end_line(self, temp_dir: Path):
        path = temp_dir / "a.py"
        path.write_text("a\nb\nc\n", encoding="utf-8")
        result = await FileEditTool().execute(
            {"path": "a.py", "start_line": 2, "new_content": "B"}, str(temp_dir)
        )
        assert result.success
        assert path.read_text(encoding="utf-8") == "a\nB\nc\n"

    @pytest.mark.asyncio
    async def test_preserves_surrounding_line_endings_byte_for_byte(self, temp_dir: Path):
        path = temp_dir / "a.py"
        path.write_bytes(b"one\r\ntwo\r\nthree\r\nfour\r\n")
        result = await FileEditTool().execute(
            {"path": "a.py", "start_line": 2, "new_content": "TWO"}, str(temp_dir)
        )
        assert result.success
        assert path.read_bytes() == b"one\r\nTWO\r\nthree\r\nfour\r\n"

    @pytest.mark.asyncio
    async def test_preserves_a_mixed_ending_file(self, temp_dir: Path):
        path = temp_dir / "a.py"
        path.write_bytes(b"one\r\ntwo\nthree\r\nfour\n")
        result = await FileEditTool().execute(
            {"path": "a.py", "start_line": 2, "new_content": "TWO"}, str(temp_dir)
        )
        assert result.success
        assert path.read_bytes() == b"one\r\nTWO\nthree\r\nfour\n"

    @pytest.mark.asyncio
    async def test_receipt_does_not_call_it_a_loosened_match(self, temp_dir: Path):
        (temp_dir / "a.py").write_text("a\nb\n", encoding="utf-8")
        result = await FileEditTool().execute(
            {"path": "a.py", "start_line": 1, "new_content": "A"}, str(temp_dir)
        )
        # A positional edit is a different addressing mode, not a fuzzy match.
        assert "addressed by line range" in result.output
        assert "loosened" not in result.output

    @pytest.mark.parametrize(
        "params,expected",
        [
            ({"start_line": 99, "new_content": "x"}, "past the end"),
            ({"start_line": 0, "new_content": "x"}, "1-based"),
            ({"start_line": 3, "end_line": 1, "new_content": "x"}, "before start_line"),
            ({"start_line": 2, "end_line": 99, "new_content": "x"}, "past the end"),
            ({"start_line": "abc", "new_content": "x"}, "Invalid start_line"),
            ({"end_line": 2, "new_content": "x"}, "start_line is required"),
        ],
    )
    @pytest.mark.asyncio
    async def test_bad_ranges_are_refused_clearly(self, temp_dir: Path, params, expected):
        (temp_dir / "a.py").write_text("a\nb\nc\n", encoding="utf-8")
        result = await FileEditTool().execute(
            {"path": "a.py", **params}, str(temp_dir)
        )
        assert result.success is False
        assert expected in result.error

    @pytest.mark.asyncio
    async def test_empty_file_has_no_editable_range(self, temp_dir: Path):
        (temp_dir / "a.py").write_text("", encoding="utf-8")
        result = await FileEditTool().execute(
            {"path": "a.py", "start_line": 1, "new_content": "x"}, str(temp_dir)
        )
        assert result.success is False
        assert "empty" in result.error


# --------------------------------------------------------------------------
# Optimistic concurrency
# --------------------------------------------------------------------------


class TestExpectedHashGuard:
    @pytest.mark.asyncio
    async def test_matching_hash_allows_the_edit(self, temp_dir: Path):
        path = temp_dir / "a.py"
        path.write_text("one\n", encoding="utf-8")
        result = await FileEditTool().execute(
            {
                "path": "a.py",
                "old_content": "one",
                "new_content": "two",
                EXPECTED_HASH_PARAM: _sha(path),
            },
            str(temp_dir),
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_stale_hash_refuses_the_edit(self, temp_dir: Path):
        path = temp_dir / "a.py"
        path.write_text("one\n", encoding="utf-8")
        stale = _sha(path)
        # Something else rewrites the file after the model read it.
        path.write_text("changed by someone else\n", encoding="utf-8")

        result = await FileEditTool().execute(
            {
                "path": "a.py",
                "old_content": "one",
                "new_content": "two",
                EXPECTED_HASH_PARAM: stale,
            },
            str(temp_dir),
        )
        assert result.success is False
        assert "changed on disk" in result.error
        assert "Re-read" in result.error
        # The file must be untouched: the guard protects content nobody reviewed.
        assert path.read_text(encoding="utf-8") == "changed by someone else\n"

    @pytest.mark.asyncio
    async def test_write_refuses_on_drift(self, temp_dir: Path):
        path = temp_dir / "a.py"
        path.write_text("one\n", encoding="utf-8")
        stale = _sha(path)
        path.write_text("newer\n", encoding="utf-8")
        result = await FileWriteTool().execute(
            {
                "path": "a.py",
                "content": "mine\n",
                "mode": "overwrite",
                EXPECTED_HASH_PARAM: stale,
            },
            str(temp_dir),
        )
        assert result.success is False
        assert "changed on disk" in result.error
        assert path.read_text(encoding="utf-8") == "newer\n"

    @pytest.mark.asyncio
    async def test_stat_to_edit_round_trip_is_clean(self, temp_dir: Path):
        path = temp_dir / "a.py"
        path.write_text("alpha\nbeta\n", encoding="utf-8")
        stat = await FileStatTool().execute({"path": "a.py"}, str(temp_dir))
        edit = await FileEditTool().execute(
            {
                "path": "a.py",
                "start_line": 1,
                "new_content": "ALPHA",
                EXPECTED_HASH_PARAM: stat.metadata["sha256"],
            },
            str(temp_dir),
        )
        assert edit.success


# --------------------------------------------------------------------------
# file_write modes
# --------------------------------------------------------------------------


class TestWriteModes:
    @pytest.mark.asyncio
    async def test_create_refuses_an_existing_file(self, temp_dir: Path):
        (temp_dir / "a.py").write_text("x", encoding="utf-8")
        result = await FileWriteTool().execute(
            {"path": "a.py", "content": "y"}, str(temp_dir)
        )
        assert result.success is False
        assert "already exists" in result.error

    @pytest.mark.asyncio
    async def test_overwrite_refuses_a_missing_file(self, temp_dir: Path):
        result = await FileWriteTool().execute(
            {"path": "ghost.py", "content": "y", "mode": "overwrite"}, str(temp_dir)
        )
        assert result.success is False
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_append_adds_without_truncating(self, temp_dir: Path):
        path = temp_dir / "log.txt"
        path.write_bytes(b"first\n")
        result = await FileWriteTool().execute(
            {"path": "log.txt", "content": "second\n", "mode": "append"}, str(temp_dir)
        )
        assert result.success
        assert path.read_text(encoding="utf-8") == "first\nsecond\n"

    @pytest.mark.asyncio
    async def test_append_supplies_a_missing_separator(self, temp_dir: Path):
        path = temp_dir / "log.txt"
        path.write_bytes(b"first")  # no trailing newline
        result = await FileWriteTool().execute(
            {"path": "log.txt", "content": "second", "mode": "append"}, str(temp_dir)
        )
        assert result.success
        assert path.read_text(encoding="utf-8") == "first\nsecond"

    @pytest.mark.asyncio
    async def test_append_creates_a_missing_file(self, temp_dir: Path):
        result = await FileWriteTool().execute(
            {"path": "fresh.txt", "content": "a\n", "mode": "append"}, str(temp_dir)
        )
        assert result.success
        assert (temp_dir / "fresh.txt").read_text(encoding="utf-8") == "a\n"

    @pytest.mark.asyncio
    async def test_forced_line_endings_win_over_the_destination(self, temp_dir: Path):
        path = temp_dir / "a.txt"
        path.write_bytes(b"crlf\r\n")
        await FileWriteTool().execute(
            {
                "path": "a.txt",
                "content": "one\ntwo\n",
                "mode": "overwrite",
                "line_endings": "lf",
            },
            str(temp_dir),
        )
        assert path.read_bytes() == b"one\ntwo\n"

    @pytest.mark.asyncio
    async def test_dominant_lf_file_is_not_restyled_by_one_stray_crlf(self, temp_dir: Path):
        path = temp_dir / "mixed.txt"
        # One CRLF among many LF lines: a naive "contains CRLF" probe rewrites
        # the whole file to CRLF, which is a spurious whole-file diff.
        path.write_bytes(b"1\n2\n3\r\n4\n5\n6\n7\n8\n")
        await FileWriteTool().execute(
            {"path": "mixed.txt", "content": "a\nb\n", "mode": "overwrite"}, str(temp_dir)
        )
        assert path.read_bytes() == b"a\nb\n"

    @pytest.mark.asyncio
    async def test_dominant_crlf_file_is_preserved(self, temp_dir: Path):
        path = temp_dir / "win.txt"
        path.write_bytes(b"1\r\n2\r\n3\r\n4\r\n")
        await FileWriteTool().execute(
            {"path": "win.txt", "content": "a\nb\n", "mode": "overwrite"}, str(temp_dir)
        )
        assert path.read_bytes() == b"a\r\nb\r\n"

    @pytest.mark.asyncio
    async def test_bom_is_preserved(self, temp_dir: Path):
        path = temp_dir / "bom.txt"
        path.write_bytes(b"\xef\xbb\xbfold\n")
        await FileWriteTool().execute(
            {"path": "bom.txt", "content": "new\n", "mode": "overwrite"}, str(temp_dir)
        )
        assert path.read_bytes().startswith(b"\xef\xbb\xbf")

    @pytest.mark.asyncio
    async def test_binary_overwrite_is_refused(self, temp_dir: Path):
        path = temp_dir / "blob.dat"
        path.write_bytes(b"\x00\x01\x02\x03\x04binary payload")
        result = await FileWriteTool().execute(
            {"path": "blob.dat", "content": "x", "mode": "overwrite"}, str(temp_dir)
        )
        assert result.success is False
        assert "not text" in result.error
        assert path.read_bytes() == b"\x00\x01\x02\x03\x04binary payload"

    @pytest.mark.asyncio
    async def test_invalid_utf8_overwrite_is_refused(self, temp_dir: Path):
        path = temp_dir / "latin.txt"
        path.write_bytes(b"caf\xe9 latin-1\n")
        result = await FileWriteTool().execute(
            {"path": "latin.txt", "content": "x", "mode": "overwrite"}, str(temp_dir)
        )
        assert result.success is False
        assert "UTF-8" in result.error
        assert path.read_bytes() == b"caf\xe9 latin-1\n"

    @pytest.mark.asyncio
    async def test_unknown_mode_is_refused(self, temp_dir: Path):
        result = await FileWriteTool().execute(
            {"path": "a.txt", "content": "x", "mode": "clobber"}, str(temp_dir)
        )
        assert result.success is False
        assert "Invalid mode" in result.error

    @pytest.mark.asyncio
    async def test_receipt_reports_real_byte_and_line_counts(self, temp_dir: Path):
        result = await FileWriteTool().execute(
            {"path": "a.txt", "content": "one\ntwo\n"}, str(temp_dir)
        )
        assert "8 byte(s)" in result.output
        assert "2 line(s)" in result.output


# --------------------------------------------------------------------------
# file_move / file_copy
# --------------------------------------------------------------------------


class TestRelocation:
    @pytest.mark.asyncio
    async def test_move_relocates_and_removes_the_source(self, temp_dir: Path):
        (temp_dir / "a.txt").write_text("data\n", encoding="utf-8")
        result = await FileMoveTool().execute(
            {"path": "a.txt", "to": "sub/b.txt"}, str(temp_dir)
        )
        assert result.success
        assert not (temp_dir / "a.txt").exists()
        assert (temp_dir / "sub" / "b.txt").read_text(encoding="utf-8") == "data\n"
        assert "source no longer exists" in result.output

    @pytest.mark.asyncio
    async def test_move_refuses_to_clobber(self, temp_dir: Path):
        (temp_dir / "a.txt").write_text("source\n", encoding="utf-8")
        (temp_dir / "b.txt").write_text("precious\n", encoding="utf-8")
        result = await FileMoveTool().execute(
            {"path": "a.txt", "to": "b.txt"}, str(temp_dir)
        )
        assert result.success is False
        assert "already exists" in result.error
        assert (temp_dir / "b.txt").read_text(encoding="utf-8") == "precious\n"
        assert (temp_dir / "a.txt").exists()

    @pytest.mark.asyncio
    async def test_copy_leaves_the_source(self, temp_dir: Path):
        (temp_dir / "a.txt").write_text("data\n", encoding="utf-8")
        result = await FileCopyTool().execute({"path": "a.txt", "to": "b.txt"}, str(temp_dir))
        assert result.success
        assert (temp_dir / "a.txt").exists()
        assert (temp_dir / "b.txt").read_text(encoding="utf-8") == "data\n"
        assert "source is unchanged" in result.output

    @pytest.mark.asyncio
    async def test_copy_refuses_to_clobber(self, temp_dir: Path):
        (temp_dir / "a.txt").write_text("a\n", encoding="utf-8")
        (temp_dir / "b.txt").write_text("b\n", encoding="utf-8")
        result = await FileCopyTool().execute({"path": "a.txt", "to": "b.txt"}, str(temp_dir))
        assert result.success is False
        assert (temp_dir / "b.txt").read_text(encoding="utf-8") == "b\n"

    @pytest.mark.asyncio
    async def test_move_honours_the_drift_guard(self, temp_dir: Path):
        path = temp_dir / "a.txt"
        path.write_text("one\n", encoding="utf-8")
        stale = _sha(path)
        path.write_text("two\n", encoding="utf-8")
        result = await FileMoveTool().execute(
            {"path": "a.txt", "to": "b.txt", EXPECTED_HASH_PARAM: stale}, str(temp_dir)
        )
        assert result.success is False
        assert "changed on disk" in result.error
        assert path.exists()

    @pytest.mark.asyncio
    async def test_missing_source_reports_not_found(self, temp_dir: Path):
        result = await FileMoveTool().execute({"path": "ghost.txt", "to": "b.txt"}, str(temp_dir))
        assert result.success is False
        assert "File not found" in result.error

    @pytest.mark.asyncio
    async def test_directory_source_is_refused(self, temp_dir: Path):
        (temp_dir / "pkg").mkdir()
        result = await FileMoveTool().execute({"path": "pkg", "to": "other"}, str(temp_dir))
        assert result.success is False
        assert "directory" in result.error

    @pytest.mark.asyncio
    async def test_moving_onto_itself_is_a_no_op(self, temp_dir: Path):
        (temp_dir / "a.txt").write_text("x", encoding="utf-8")
        result = await FileMoveTool().execute({"path": "a.txt", "to": "a.txt"}, str(temp_dir))
        assert result.success
        assert "same path" in result.output


# --------------------------------------------------------------------------
# Destructive-operation safety
# --------------------------------------------------------------------------


class TestDeleteSafety:
    @pytest.mark.asyncio
    async def test_workspace_root_cannot_be_deleted(self, temp_dir: Path):
        (temp_dir / "keep.txt").write_text("precious\n", encoding="utf-8")
        result = await FileDeleteTool().execute({"path": "."}, str(temp_dir))
        assert result.success is False
        assert "workspace root" in result.error
        assert (temp_dir / "keep.txt").exists()

    @pytest.mark.asyncio
    async def test_symlinked_directory_is_not_followed(self, temp_dir: Path):
        outside = temp_dir.parent / "outside_target"
        outside.mkdir(exist_ok=True)
        (outside / "precious.txt").write_text("do not delete me\n", encoding="utf-8")
        link = temp_dir / "link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation not permitted on this host")

        result = await FileDeleteTool().execute({"path": "link"}, str(temp_dir))
        assert result.success is False
        assert "symlink" in result.error.lower() or "outside" in result.error.lower()
        assert (outside / "precious.txt").exists()

    @pytest.mark.asyncio
    async def test_directory_delete_reports_what_it_removed(self, temp_dir: Path):
        # "build/" is excluded by the default ignore rules, so use a name the
        # agent is actually allowed to touch.
        (temp_dir / "outdir").mkdir()
        (temp_dir / "outdir" / "a.o").write_text("x", encoding="utf-8")
        (temp_dir / "outdir" / "sub").mkdir()
        (temp_dir / "outdir" / "sub" / "b.o").write_text("y", encoding="utf-8")
        result = await FileDeleteTool().execute({"path": "outdir"}, str(temp_dir))
        assert result.success
        assert "3 entries" in result.output
        assert not (temp_dir / "outdir").exists()

    @pytest.mark.asyncio
    async def test_file_delete_reports_bytes_removed(self, temp_dir: Path):
        (temp_dir / "a.txt").write_text("12345", encoding="utf-8")
        result = await FileDeleteTool().execute({"path": "a.txt"}, str(temp_dir))
        assert result.success
        assert "5 byte(s) removed" in result.output
        assert "no longer exists" in result.output


# --------------------------------------------------------------------------
# apply_patch relocation and content
# --------------------------------------------------------------------------


class TestPatchRelocation:
    @pytest.mark.asyncio
    async def test_pure_rename_needs_no_content_hunk(self, temp_dir: Path):
        (temp_dir / "old.py").write_text("x = 1\n", encoding="utf-8")
        patch = (
            "*** Begin Patch\n"
            "*** Update File: old.py\n"
            "*** Move to: new.py\n"
            "*** End Patch\n"
        )
        result = await ApplyPatchTool().execute({"patch": patch}, str(temp_dir))
        assert result.success
        assert not (temp_dir / "old.py").exists()
        assert (temp_dir / "new.py").read_text(encoding="utf-8") == "x = 1\n"
        assert "R old.py -> new.py" in result.output

    @pytest.mark.asyncio
    async def test_rename_onto_an_existing_path_is_refused(self, temp_dir: Path):
        (temp_dir / "a.py").write_text("a\n", encoding="utf-8")
        (temp_dir / "b.py").write_text("b\n", encoding="utf-8")
        patch = (
            "*** Begin Patch\n"
            "*** Update File: a.py\n"
            "*** Move to: b.py\n"
            "*** End Patch\n"
        )
        result = await ApplyPatchTool().execute({"patch": patch}, str(temp_dir))
        assert result.success is False
        assert "already exists" in result.error
        assert (temp_dir / "b.py").read_text(encoding="utf-8") == "b\n"
        assert (temp_dir / "a.py").exists()

    @pytest.mark.asyncio
    async def test_update_without_hunk_and_without_move_is_still_an_error(
        self, temp_dir: Path
    ):
        (temp_dir / "a.py").write_text("a\n", encoding="utf-8")
        patch = "*** Begin Patch\n*** Update File: a.py\n*** End Patch\n"
        result = await ApplyPatchTool().execute({"patch": patch}, str(temp_dir))
        assert result.success is False
        assert "@@" in result.error

    @pytest.mark.asyncio
    async def test_asterisks_inside_code_do_not_end_the_hunk(self, temp_dir: Path):
        (temp_dir / "doc.py").write_text("def f():\n    pass\n", encoding="utf-8")
        patch = (
            "*** Begin Patch\n"
            "*** Update File: doc.py\n"
            "@@\n"
            " def f():\n"
            "+    # *** important note\n"
            "     pass\n"
            "*** End Patch\n"
        )
        result = await ApplyPatchTool().execute({"patch": patch}, str(temp_dir))
        assert result.success
        assert "# *** important note" in (temp_dir / "doc.py").read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_end_of_file_marker_still_works(self, temp_dir: Path):
        (temp_dir / "a.py").write_text("a\nb\n", encoding="utf-8")
        patch = (
            "*** Begin Patch\n"
            "*** Update File: a.py\n"
            "@@\n"
            "-b\n"
            "+B\n"
            "*** End of File\n"
            "*** End Patch\n"
        )
        result = await ApplyPatchTool().execute({"patch": patch}, str(temp_dir))
        assert result.success
        assert (temp_dir / "a.py").read_text(encoding="utf-8") == "a\nB\n"
