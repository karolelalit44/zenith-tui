"""Contracts for the mutation journal and the revert path.

The journal is what makes an agent's file changes reviewable and reversible.
Without it, "undo that" means a shell `git checkout`, which is wrong for files
that were never committed, and a failed multi-step edit leaves the workspace in
a state nobody asked for. These tests pin both properties.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from server.agents.session_workspace import get_cached_read, reset_session
from server.toolkit.journal import JOURNAL
from server.toolkit.registry import current_tool_session_id
from server.toolkit.tools.file_delete import FileDeleteTool
from server.toolkit.tools.file_edit import FileEditTool
from server.toolkit.tools.file_move import FileMoveTool
from server.toolkit.tools.file_read import FileReadTool
from server.toolkit.tools.file_write import FileWriteTool

_SESSION = "test-journal"


@pytest.fixture
def session_ctx():
    JOURNAL.clear(_SESSION)
    reset_session(_SESSION)
    token = current_tool_session_id.set(_SESSION)
    yield _SESSION
    current_tool_session_id.reset(token)
    JOURNAL.clear(_SESSION)
    reset_session(_SESSION)


async def _mutate(temp_dir: Path) -> None:
    # Written as bytes: text mode on Windows rewrites \n to \r\n, which would
    # make the expected pre-images below host-dependent.
    (temp_dir / "edit.txt").write_bytes(b"original\n")
    (temp_dir / "gone.txt").write_bytes(b"will be deleted\n")
    (temp_dir / "keep.txt").write_bytes(b"untouched\n")
    await FileWriteTool().execute(
        {"path": "edit.txt", "content": "rewritten\n", "mode": "overwrite"}, str(temp_dir)
    )
    await FileEditTool().execute(
        {"path": "edit.txt", "old_content": "rewritten", "new_content": "edited"}, str(temp_dir)
    )
    await FileWriteTool().execute({"path": "created.txt", "content": "new file\n"}, str(temp_dir))
    await FileDeleteTool().execute({"path": "gone.txt"}, str(temp_dir))
    await FileMoveTool().execute({"path": "created.txt", "to": "moved.txt"}, str(temp_dir))


class TestJournalRecording:
    @pytest.mark.asyncio
    async def test_every_mutator_is_recorded(self, temp_dir: Path, session_ctx):
        await _mutate(temp_dir)
        tools = {e.tool for e in JOURNAL.entries(_SESSION)}
        assert tools == {"file_write", "file_edit", "file_delete", "file_move"}

    @pytest.mark.asyncio
    async def test_actions_are_classified(self, temp_dir: Path, session_ctx):
        await _mutate(temp_dir)
        actions = {(e.tool, e.action) for e in JOURNAL.entries(_SESSION)}
        assert ("file_write", "modify") in actions
        assert ("file_delete", "delete") in actions

    @pytest.mark.asyncio
    async def test_pre_image_is_captured(self, temp_dir: Path, session_ctx):
        await _mutate(temp_dir)
        first = JOURNAL.entries(_SESSION)[0]
        assert first.before == b"original\n"
        assert first.after == b"rewritten\n"

    @pytest.mark.asyncio
    async def test_untouched_files_are_not_recorded(self, temp_dir: Path, session_ctx):
        await _mutate(temp_dir)
        assert not any(e.path.endswith("keep.txt") for e in JOURNAL.entries(_SESSION))

    @pytest.mark.asyncio
    async def test_no_session_id_means_no_journal_entry(self, temp_dir: Path):
        (temp_dir / "a.txt").write_text("x", encoding="utf-8")
        token = current_tool_session_id.set("")
        try:
            await FileWriteTool().execute(
                {"path": "a.txt", "content": "y", "mode": "overwrite"}, str(temp_dir)
            )
        finally:
            current_tool_session_id.reset(token)
        assert JOURNAL.entries("") == []

    @pytest.mark.asyncio
    async def test_oversized_file_is_journaled_by_size_only(self, temp_dir: Path, session_ctx):
        from server.toolkit.journal import MAX_JOURNALLED_BYTES

        big = temp_dir / "big.txt"
        big.write_bytes(b"x" * (MAX_JOURNALLED_BYTES + 1))
        await FileWriteTool().execute(
            {"path": "big.txt", "content": "y", "mode": "overwrite"}, str(temp_dir)
        )
        entry = JOURNAL.entries(_SESSION)[0]
        assert entry.content_omitted is True
        assert entry.bytes_before > MAX_JOURNALLED_BYTES
        # The size is still reported, so the change is visible even if not undoable.
        assert "too large" in entry.describe()


class TestRevert:
    @pytest.mark.asyncio
    async def test_revert_restores_every_earlier_state(self, temp_dir: Path, session_ctx):
        await _mutate(temp_dir)
        restored, failed, _ = JOURNAL.revert(_SESSION, 0)

        assert failed == []
        # write, edit, create, delete, and the two halves of the move.
        assert restored == 6
        assert (temp_dir / "edit.txt").read_bytes() == b"original\n"
        assert (temp_dir / "gone.txt").read_bytes() == b"will be deleted\n"
        assert not (temp_dir / "created.txt").exists()
        assert not (temp_dir / "moved.txt").exists()
        assert (temp_dir / "keep.txt").read_bytes() == b"untouched\n"

    @pytest.mark.asyncio
    async def test_revert_empties_the_journal(self, temp_dir: Path, session_ctx):
        await _mutate(temp_dir)
        JOURNAL.revert(_SESSION, 0)
        assert JOURNAL.entries(_SESSION) == []

    @pytest.mark.asyncio
    async def test_partial_revert_keeps_the_earlier_entries(
        self, temp_dir: Path, session_ctx
    ):
        await _mutate(temp_dir)
        entries = JOURNAL.entries(_SESSION)
        # `since` is exclusive, so passing the first entry's seq undoes everything
        # after it and leaves the first write in place.
        restored, failed, _ = JOURNAL.revert(_SESSION, entries[0].seq)

        assert failed == []
        assert (temp_dir / "edit.txt").read_text(encoding="utf-8") == "rewritten\n"
        # The delete happened after the cut, so undoing it brings the file back.
        assert (temp_dir / "gone.txt").read_bytes() == b"will be deleted\n"
        # The create and the move also happened after the cut.
        assert not (temp_dir / "created.txt").exists()
        assert not (temp_dir / "moved.txt").exists()
        assert [e.seq for e in JOURNAL.entries(_SESSION)] == [entries[0].seq]

    @pytest.mark.asyncio
    async def test_revert_is_idempotent(self, temp_dir: Path, session_ctx):
        await _mutate(temp_dir)
        JOURNAL.revert(_SESSION, 0)
        second_restored, second_failed, _ = JOURNAL.revert(_SESSION, 0)
        assert second_restored == 0
        assert second_failed == []

    @pytest.mark.asyncio
    async def test_failures_are_reported_not_swallowed(self, temp_dir: Path, session_ctx, monkeypatch):
        await _mutate(temp_dir)
        original = Path.write_bytes

        def deny(self, *args, **kwargs):
            if self.name == "edit.txt":
                raise PermissionError(13, "denied")
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "write_bytes", deny)
        restored, failed, _ = JOURNAL.revert(_SESSION, 0)

        assert failed, "a failed restore must be named, not reported as clean"
        assert any("edit.txt" in p for p in failed)

    @pytest.mark.asyncio
    async def test_revert_drops_stale_read_cache_entries(
        self, temp_dir: Path, session_ctx
    ):
        path = temp_dir / "cached.txt"
        path.write_text("before\n", encoding="utf-8")
        await FileReadTool().execute({"path": "cached.txt"}, str(temp_dir))
        stat = path.stat()
        assert get_cached_read(_SESSION, str(path.resolve()), 0, 250, stat.st_mtime_ns, stat.st_size)

        await FileWriteTool().execute(
            {"path": "cached.txt", "content": "after\n", "mode": "overwrite"}, str(temp_dir)
        )
        JOURNAL.revert(_SESSION, 0)
        reset_session(_SESSION)

        stat = path.stat()
        # After a revert the cache must not be able to serve the pre-revert text.
        assert get_cached_read(_SESSION, str(path.resolve()), 0, 250, stat.st_mtime_ns, stat.st_size) is None

    @pytest.mark.asyncio
    async def test_revert_refuses_to_unlink_modified_file_when_content_omitted(
        self, temp_dir: Path, session_ctx
    ):
        from server.toolkit.journal import MAX_JOURNALLED_BYTES

        big = temp_dir / "big.txt"
        big.write_bytes(b"x" * (MAX_JOURNALLED_BYTES + 1))
        await FileWriteTool().execute(
            {"path": "big.txt", "content": "modified\n", "mode": "overwrite"}, str(temp_dir)
        )
        assert big.read_bytes() == b"modified\n"
        restored, failed, _ = JOURNAL.revert(_SESSION, 0)
        assert failed == [str(big.resolve())]
        # The modified file must NOT be unlinked on revert when content was omitted!
        assert big.exists()
        assert big.read_bytes() == b"modified\n"

    @pytest.mark.asyncio
    async def test_revert_directory_delete_is_reported_as_failed(
        self, temp_dir: Path, session_ctx
    ):
        subdir = temp_dir / "sub"
        subdir.mkdir()
        (subdir / "file.txt").write_text("hello", encoding="utf-8")
        await FileDeleteTool().execute({"path": "sub"}, str(temp_dir))
        assert not subdir.exists()
        restored, failed, _ = JOURNAL.revert(_SESSION, 0)
        assert str(subdir.resolve()) in failed
        assert restored == 0

    @pytest.mark.asyncio
    async def test_apply_patch_move_reverts_both_paths(
        self, temp_dir: Path, session_ctx
    ):
        from server.toolkit.tools.apply_patch import ApplyPatchTool

        (temp_dir / "orig.txt").write_text("line1\nline2\n", encoding="utf-8")
        patch = (
            "*** Begin Patch\n"
            "*** Update File: orig.txt\n"
            "*** Move To: ren.txt\n"
            "@@\n"
            " line1\n"
            "-line2\n"
            "+line2_edited\n"
            "*** End Patch"
        )
        res = await ApplyPatchTool().execute({"patch": patch}, str(temp_dir))
        assert res.success is True
        assert not (temp_dir / "orig.txt").exists()
        assert (temp_dir / "ren.txt").read_text(encoding="utf-8") == "line1\nline2_edited\n"

        restored, failed, _ = JOURNAL.revert(_SESSION, 0)
        assert failed == []
        assert restored == 2
        assert (temp_dir / "orig.txt").read_text(encoding="utf-8") == "line1\nline2\n"
        assert not (temp_dir / "ren.txt").exists()
