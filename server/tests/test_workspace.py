import subprocess

import pytest

from server.workspace.git import GitOps


def _has_git() -> bool:
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


HAS_GIT = _has_git()


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
            ["git", "config", "user.email", "test@test.com"], cwd=str(temp_dir), capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=str(temp_dir), capture_output=True
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
            ["git", "config", "user.email", "test@test.com"], cwd=str(temp_dir), capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=str(temp_dir), capture_output=True
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
            ["git", "config", "user.email", "test@test.com"], cwd=str(temp_dir), capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=str(temp_dir), capture_output=True
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
            ["git", "config", "user.email", "test@test.com"], cwd=str(temp_dir), capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=str(temp_dir), capture_output=True
        )
        (temp_dir / "file.txt").write_text("content")
        git = GitOps(str(temp_dir))
        git.commit("First commit")
        log = git.log()
        assert len(log) >= 1
        assert log[0]["message"] == "First commit"

