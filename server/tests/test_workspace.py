"""Tests for workspace: git operations, file tracker, repo map."""

import subprocess

import pytest

from server.workspace.git import GitOps
from server.workspace.repo_map import RepoMap
from server.workspace.tracker import FileTracker


def _has_git() -> bool:
    """Check if git is available on the system."""
    try:
        result = subprocess.run(
            ["git", "--version"], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


HAS_GIT = _has_git()


# ── Git Operations ─────────────────────────────────────────────────


class TestGitOps:
    def test_not_git_repo(self, temp_dir):
        git = GitOps(str(temp_dir))
        assert git.find_git_root() is None
        assert git.is_git_repo() is False

    def test_status_not_repo(self, temp_dir):
        git = GitOps(str(temp_dir))
        status = git.status()
        assert status.get("is_git_repo") is False
        assert "error" in status

    def test_commit_not_repo(self, temp_dir):
        git = GitOps(str(temp_dir))
        result = git.commit("test")
        assert result["success"] is False

    def test_diff_not_repo(self, temp_dir):
        git = GitOps(str(temp_dir))
        diff = git.diff()
        assert "Not a git repository" in diff or "error" in diff.lower()

    def test_log_not_repo(self, temp_dir):
        git = GitOps(str(temp_dir))
        log = git.log()
        assert log == []

    def test_undo_not_repo(self, temp_dir):
        git = GitOps(str(temp_dir))
        result = git.undo()
        assert result["success"] is False

    def test_get_repo_info_not_repo(self, temp_dir):
        git = GitOps(str(temp_dir))
        info = git.get_repo_info()
        assert info["is_git_repo"] is False

    def test_is_gitignored_not_repo(self, temp_dir):
        git = GitOps(str(temp_dir))
        assert git.is_gitignored("any_file.txt") is False

    @pytest.mark.skipif(not HAS_GIT, reason="git not available")
    def test_git_repo_detection(self, temp_dir):
        subprocess.run(["git", "init"], cwd=str(temp_dir), capture_output=True)
        git = GitOps(str(temp_dir))
        assert git.is_git_repo() is True
        root = git.find_git_root()
        assert root is not None
        assert (root / ".git").exists()

    @pytest.mark.skipif(not HAS_GIT, reason="git not available")
    def test_git_status(self, temp_dir):
        subprocess.run(["git", "init"], cwd=str(temp_dir), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(temp_dir), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(temp_dir), capture_output=True,
        )
        (temp_dir / "new_file.txt").write_text("hello")
        git = GitOps(str(temp_dir))
        status = git.status()
        assert status["is_git_repo"] is True
        assert "new_file.txt" in status["untracked"]

    @pytest.mark.skipif(not HAS_GIT, reason="git not available")
    def test_git_commit(self, temp_dir):
        subprocess.run(["git", "init"], cwd=str(temp_dir), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(temp_dir), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(temp_dir), capture_output=True,
        )
        (temp_dir / "file.txt").write_text("content")
        git = GitOps(str(temp_dir))
        result = git.commit("Initial commit")
        assert result["success"] is True
        assert "hash" in result

    @pytest.mark.skipif(not HAS_GIT, reason="git not available")
    def test_git_diff(self, temp_dir):
        subprocess.run(["git", "init"], cwd=str(temp_dir), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(temp_dir), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(temp_dir), capture_output=True,
        )
        (temp_dir / "file.txt").write_text("initial")
        git = GitOps(str(temp_dir))
        git.commit("init")
        (temp_dir / "file.txt").write_text("modified")
        diff = git.diff()
        assert "modified" in diff or "file.txt" in diff

    @pytest.mark.skipif(not HAS_GIT, reason="git not available")
    def test_git_log(self, temp_dir):
        subprocess.run(["git", "init"], cwd=str(temp_dir), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(temp_dir), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(temp_dir), capture_output=True,
        )
        (temp_dir / "file.txt").write_text("content")
        git = GitOps(str(temp_dir))
        git.commit("First commit")
        log = git.log()
        assert len(log) >= 1
        assert log[0]["message"] == "First commit"


# ── File Tracker ────────────────────────────────────────────────────


class TestFileTracker:
    def test_track_file(self):
        tracker = FileTracker(".")
        tracker.track("test.py", "create")
        assert tracker.has_changes()
        assert "test.py" in tracker.get_changed_files()

    def test_track_multiple(self):
        tracker = FileTracker(".")
        tracker.track("a.py", "create")
        tracker.track("b.py", "edit")
        assert len(tracker.get_changed_files()) == 2

    def test_get_summary(self):
        tracker = FileTracker(".")
        tracker.track("a.py", "create")
        tracker.track("b.py", "create")
        summary = tracker.get_summary()
        assert "2" in summary
        assert "create" in summary

    def test_empty_summary(self):
        tracker = FileTracker(".")
        assert tracker.get_summary() == "No files changed."

    def test_clear(self):
        tracker = FileTracker(".")
        tracker.track("a.py", "create")
        tracker.clear()
        assert not tracker.has_changes()

    def test_get_files_by_operation(self):
        tracker = FileTracker(".")
        tracker.track("a.py", "create")
        tracker.track("b.py", "edit")
        creates = tracker.get_files_by_operation("create")
        assert creates == ["a.py"]

    def test_content_capped(self):
        tracker = FileTracker(".")
        big_content = "x" * 20000
        tracker.track("big.txt", "create", big_content)
        changes = tracker.get_changes()
        assert len(changes["big.txt"]["content"]) <= 10000


# ── Repo Map ────────────────────────────────────────────────────────


class TestRepoMap:
    def test_get_structure(self, temp_dir):
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "main.py").write_text("print('hello')")
        (temp_dir / "README.md").write_text("# Test")
        repo = RepoMap(str(temp_dir))
        structure = repo.get_structure()
        assert structure["name"] == temp_dir.name
        assert structure["type"] == "directory"
        assert len(structure["children"]) > 0

    def test_get_summary(self, temp_dir):
        (temp_dir / "app.py").write_text("")
        (temp_dir / "utils.py").write_text("")
        (temp_dir / "index.ts").write_text("")
        repo = RepoMap(str(temp_dir))
        summary = repo.get_summary()
        assert "Python" in summary
        assert "TypeScript" in summary
        assert "3" in summary

    def test_empty_repo_summary(self, temp_dir):
        repo = RepoMap(str(temp_dir))
        summary = repo.get_summary()
        assert "Empty" in summary

    def test_get_key_files(self, temp_dir):
        (temp_dir / "README.md").write_text("# Test")
        (temp_dir / "package.json").write_text("{}")
        repo = RepoMap(str(temp_dir))
        key_files = repo.get_key_files()
        assert "README.md" in key_files
        assert "package.json" in key_files

    def test_skip_dirs(self, temp_dir):
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "main.py").write_text("")
        (temp_dir / "node_modules").mkdir()
        (temp_dir / "node_modules" / "pkg").mkdir()
        (temp_dir / "__pycache__").mkdir()
        repo = RepoMap(str(temp_dir))
        structure = repo.get_structure()
        child_names = [c["name"] for c in structure["children"]]
        assert "node_modules" not in child_names
        assert "__pycache__" not in child_names
        assert "src" in child_names

    def test_max_depth(self, temp_dir):
        (temp_dir / "a").mkdir()
        (temp_dir / "a" / "b").mkdir()
        (temp_dir / "a" / "b" / "c").mkdir()
        (temp_dir / "a" / "b" / "c" / "deep.py").write_text("")
        repo = RepoMap(str(temp_dir))
        structure = repo.get_structure(max_depth=2)
        assert any(c["name"] == "a" for c in structure["children"])

    def test_get_file_count(self, temp_dir):
        (temp_dir / "a.py").write_text("")
        (temp_dir / "b.py").write_text("")
        (temp_dir / "c.txt").write_text("")
        repo = RepoMap(str(temp_dir))
        assert repo.get_file_count() == 3
