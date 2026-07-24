"""Git operations — subprocess-based git integration."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GitOps:
    """Git operations via subprocess. Handles root detection, status, commit, diff, undo."""

    def __init__(self, workspace_root: str) -> None:
        self.root = Path(workspace_root).resolve()
        self._git_root: Optional[Path] = None

    def find_git_root(self) -> Optional[Path]:
        """Find the .git directory by walking up from workspace root."""
        if self._git_root is not None:
            return self._git_root

        current = self.root
        while current != current.parent:
            if (current / ".git").exists():
                self._git_root = current
                return current
            current = current.parent
        return None

    def is_git_repo(self) -> bool:
        """Check if workspace is inside a git repository."""
        return self.find_git_root() is not None

    def _run(self, *args: str, timeout: int = 30) -> tuple[int, str, str]:
        """Run a git command and return (exit_code, stdout, stderr)."""
        root = self.find_git_root()
        if not root:
            return -1, "", "Not a git repository"

        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            return result.returncode, result.stdout, result.stderr
        except FileNotFoundError:
            return -1, "", "git executable not found"
        except subprocess.TimeoutExpired:
            return -1, "", f"git command timed out after {timeout}s"
        except Exception as e:
            return -1, "", str(e)

    def status(self) -> dict:
        """Get git status: branch, modified, staged, untracked files."""
        code, stdout, stderr = self._run("status", "--porcelain")
        if code != 0:
            return {"error": stderr, "is_git_repo": False}

        branch_code, branch_out, _ = self._run("branch", "--show-current")
        branch = branch_out.strip() if branch_code == 0 else "unknown"

        modified: list[str] = []
        staged: list[str] = []
        untracked: list[str] = []

        for line in stdout.strip().split("\n"):
            if not line:
                continue
            status_code = line[:2]
            file_path = line[3:]

            if status_code[0] in "MADRC":
                staged.append(file_path)
            elif status_code[1] in "MADRC":
                modified.append(file_path)
            elif status_code == "??":
                untracked.append(file_path)

        return {
            "branch": branch,
            "modified": modified,
            "staged": staged,
            "untracked": untracked,
            "clean": len(modified) == 0 and len(staged) == 0 and len(untracked) == 0,
            "is_git_repo": True,
        }

    def commit(self, message: str, files: list[str] | None = None) -> dict:
        """Stage files and commit. If files is None, stages all changes."""
        if files:
            for f in files:
                add_code, _, add_err = self._run("add", "--", f)
                if add_code != 0:
                    return {"success": False, "error": f"Failed to stage {f}: {add_err}"}
        else:
            add_code, _, add_err = self._run("add", "-A")
            if add_code != 0:
                return {"success": False, "error": f"Failed to stage: {add_err}"}

        code, stdout, stderr = self._run("commit", "-m", message)
        if code != 0:
            if "nothing to commit" in stderr or "nothing to commit" in stdout:
                return {"success": False, "error": "Nothing to commit"}
            return {"success": False, "error": stderr}

        hash_code, hash_out, _ = self._run("rev-parse", "HEAD")
        return {
            "success": True,
            "hash": hash_out.strip() if hash_code == 0 else "unknown",
            "message": message,
        }

    def diff(self, file_path: str | None = None) -> str:
        """Show diff of unstaged changes."""
        args = ["diff"]
        if file_path:
            args.extend(["--", file_path])
        code, stdout, stderr = self._run(*args)
        return stdout if code == 0 else stderr

    def diff_staged(self) -> str:
        """Show diff of staged changes."""
        code, stdout, stderr = self._run("diff", "--cached")
        return stdout if code == 0 else stderr

    def diffstat(self) -> str:
        """Show diffstat summary."""
        code, stdout, stderr = self._run("diff", "--stat")
        return stdout if code == 0 else stderr

    def log(self, count: int = 10) -> list[dict]:
        """Get recent commit log."""
        code, stdout, stderr = self._run(
            "log", f"--max-count={count}", "--pretty=format:%H|%s|%an|%ai"
        )
        if code != 0:
            return []

        commits = []
        for line in stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) >= 4:
                commits.append({
                    "hash": parts[0][:8],
                    "message": parts[1],
                    "author": parts[2],
                    "date": parts[3],
                })
        return commits

    def undo(self) -> dict:
        """Revert the last commit."""
        status = self.status()
        if status.get("error"):
            return {"success": False, "error": status["error"]}

        code, stdout, stderr = self._run("revert", "HEAD", "--no-edit")
        if code != 0:
            return {"success": False, "error": stderr}

        return {"success": True, "message": "Reverted last commit"}

    def is_gitignored(self, file_path: str) -> bool:
        """Check if a file is gitignored."""
        code, _, _ = self._run("check-ignore", "--no-index", file_path)
        return code == 0

    def get_repo_info(self) -> dict:
        """Get repository information."""
        root = self.find_git_root()
        if not root:
            return {"is_git_repo": False}

        remote_code, remote_out, _ = self._run("remote", "get-url", "origin")
        return {
            "is_git_repo": True,
            "root": str(root),
            "remote": remote_out.strip() if remote_code == 0 else None,
            "status": self.status(),
        }
