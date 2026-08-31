"""Tests for cached workspace statistics (workspace/index.py)."""

import pytest

from server.workspace.ignore import clear_matcher_cache
from server.workspace.index import (
    WorkspaceStats,
    get_workspace_stats,
    invalidate_workspace_stats,
)


@pytest.fixture(autouse=True)
def _clean_ignore_and_stats():
    clear_matcher_cache()
    yield
    clear_matcher_cache()


class TestWorkspaceStats:
    def test_counts_files_and_top_level_dirs(self, temp_dir):
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "a.py").write_text("")
        (temp_dir / "src" / "b.py").write_text("")
        (temp_dir / "README.md").write_text("")
        stats = get_workspace_stats(temp_dir)
        assert stats.total_files == 3
        assert stats.top_level.get("src") == 2
        assert stats.top_level.get("") == 1  # root-level files
        assert stats.truncated is False

    def test_nested_files_roll_up_to_top_level(self, temp_dir):
        (temp_dir / "pkg").mkdir(parents=True)
        (temp_dir / "pkg" / "sub").mkdir()
        (temp_dir / "pkg" / "sub" / "mod.py").write_text("")
        stats = get_workspace_stats(temp_dir)
        assert stats.total_files == 1
        assert stats.top_level.get("pkg") == 1

    def test_ignored_files_excluded(self, temp_dir):
        (temp_dir / "node_modules").mkdir()
        (temp_dir / "node_modules" / "v.js").write_text("")
        (temp_dir / "app.js").write_text("")
        stats = get_workspace_stats(temp_dir)
        assert stats.total_files == 1

    def test_invalidate_forces_refresh(self, temp_dir):
        (temp_dir / "a.py").write_text("")
        get_workspace_stats(temp_dir)
        (temp_dir / "b.py").write_text("")
        stats = get_workspace_stats(temp_dir)
        assert stats.total_files == 1  # cached, stale
        invalidate_workspace_stats(temp_dir)
        stats = get_workspace_stats(temp_dir)
        assert stats.total_files == 2

    def test_describe_top_level_bounded(self, temp_dir):
        for i in range(20):
            d = temp_dir / f"dir{i}"
            d.mkdir()
            (d / "f.py").write_text("")
        stats = get_workspace_stats(temp_dir)
        description = stats.describe_top_level(max_entries=5)
        assert "+" in description  # truncated with "+N more"

    def test_describe_top_level_labels_root_files(self, temp_dir):
        (temp_dir / "a.py").write_text("")
        stats = get_workspace_stats(temp_dir)
        description = stats.describe_top_level()
        assert "(root files: 1)" in description


class TestWorkspaceStatsDataclass:
    def test_defaults(self):
        stats = WorkspaceStats(total_files=0)
        assert stats.top_level == {}
        assert stats.truncated is False
