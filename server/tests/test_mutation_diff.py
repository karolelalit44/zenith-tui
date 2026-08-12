"""Regression tests for git-native unified-diff capture on file mutations.

Covers the ``build_tool_metadata`` diff emission consumed by the TUI's unified
Git diff viewer (write / edit), plus ``GitOps.diff_path`` handling of brand-new
untracked files via intent-to-add.
"""

import subprocess
from pathlib import Path

from server.toolkit.base import ToolResult
from server.toolkit.executor import build_tool_metadata
from server.workspace.git import GitOps


def _run_git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _init_git(root: Path) -> None:
    """Seed a throwaway git repo with one tracked base file."""
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    _run_git(root, "init", "-q")
    _run_git(root, "config", "user.email", "test@example.com")
    _run_git(root, "config", "user.name", "Test")
    _run_git(root, "add", "-A")
    _run_git(root, "commit", "-m", "init")


class TestBuildToolMetadataDiff:
    def test_file_write_captures_git_diff_for_new_file(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        _init_git(workspace)
        (workspace / "app.py").write_text("x = 1\ny = 2\n", encoding="utf-8")

        result = ToolResult(success=True, output="Created app.py", metadata={})
        meta = build_tool_metadata(
            "file_write",
            {"path": "app.py", "content": "x = 1\ny = 2\n"},
            result,
            12,
            str(workspace),
        )

        diff = meta.get("diff", "")
        assert diff
        assert "diff --git" in diff
        assert "+x = 1" in diff
        assert "+y = 2" in diff

    def test_file_edit_keeps_tool_reported_difflib_patch(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "a.py").write_text("old\n", encoding="utf-8")
        patch = "@@ -1 +1 @@\n-old\n+new\n"
        result = ToolResult(
            success=True,
            output="Edited a.py",
            metadata={"diff": patch, "changes": 1, "match": "exact"},
        )
        meta = build_tool_metadata(
            "file_edit",
            {"path": "a.py", "old_content": "old", "new_content": "new"},
            result,
            8,
            str(ws),
        )
        assert meta.get("diff") == patch

    def test_multi_edit_emits_diff(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "b.txt").write_text("alpha\n", encoding="utf-8")
        patch = "@@ -1 +1 @@\n-alpha\n+beta\n"
        result = ToolResult(
            success=True,
            output="Applied 1 edit(s) to b.txt",
            metadata={"diff": patch, "edits_applied": 1},
        )
        meta = build_tool_metadata(
            "multi_edit",
            {"filepath": "b.txt"},
            result,
            9,
            str(ws),
        )
        assert "beta" in meta.get("diff", "")


class TestGitOpsDiffPath:
    def test_untracked_file_returns_unified_diff_via_intent_to_add(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        _init_git(ws)
        (ws / "note.md").write_text("line1\nline2\n", encoding="utf-8")

        git = GitOps(str(ws))
        diff = git.diff_path("note.md")
        assert "diff --git" in diff
        assert "+line1" in diff
        assert "+line2" in diff

    def test_tracked_modified_file_returns_diff(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        _init_git(ws)
        (ws / "base.txt").write_text("changed\n", encoding="utf-8")

        git = GitOps(str(ws))
        diff = git.diff_path("base.txt")
        assert "diff --git" in diff
        assert "-base" in diff
        assert "+changed" in diff

    def test_clean_file_returns_empty(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        _init_git(ws)
        git = GitOps(str(ws))
        assert git.diff_path("base.txt") == ""
