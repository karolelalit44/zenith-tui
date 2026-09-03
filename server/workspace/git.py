from __future__ import annotations
import logging
import os
import subprocess
from pathlib import Path
from server.config.env import optional_int


logger = logging.getLogger(__name__)
_GIT_TIMEOUT_DEFAULT = 30


def _git_timeout() -> int:
    raw = os.environ.get("ZENITH_GIT_TIMEOUT", "").strip()
    if not raw:
        return _GIT_TIMEOUT_DEFAULT
    return optional_int("ZENITH_GIT_TIMEOUT", _GIT_TIMEOUT_DEFAULT)


class GitOps:
    def __init__(self, workspace_root: str) -> None:
        self.root = Path(workspace_root).resolve()
        self._git_root: Path | None = None

    def find_git_root(self) -> Path | None:
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
        return self.find_git_root() is not None

    def _run(self, *args: str, timeout: int | None = None) -> tuple[int, str, str]:
        root = self.find_git_root()
        if not root:
            return (-1, "", "Not a git repository")
        if timeout is None:
            timeout = _git_timeout()
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            return (result.returncode, result.stdout, result.stderr)
        except FileNotFoundError:
            return (-1, "", "git executable not found")
        except subprocess.TimeoutExpired:
            return (-1, "", f"git command timed out after {timeout}s")

    def status(self) -> dict:
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
            "clean": len(modified) == 0 and len(staged) == 0 and (len(untracked) == 0),
            "is_git_repo": True,
        }

    def commit(self, message: str, files: list[str] | None = None) -> dict:
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
        args = ["diff"]
        if file_path:
            args.extend(["--", file_path])
        code, stdout, stderr = self._run(*args)
        return stdout if code == 0 else stderr

    def diff_path(self, file_path: str) -> str:
        """Unified diff for a working-tree path, including untracked files.

        Untracked files are registered with intent-to-add (``git add -N``) so
        ``git diff`` reports their full contents as additions without staging
        anything. Returns an empty string when no diff is available.
        """
        if not self.is_git_repo():
            return ""
        code, stdout, _ = self._run("diff", "--", file_path)
        if code != 0:
            return ""
        if stdout:
            return stdout
        status_code, status_out, _ = self._run("status", "--porcelain", "--", file_path)
        if status_code != 0:
            return ""
        untracked = any(line.startswith("??") for line in status_out.splitlines())
        if not untracked:
            return ""
        add_code, _, _ = self._run("add", "-N", "--", file_path)
        if add_code != 0:
            return ""
        diff_code, diff_out, _ = self._run("diff", "--", file_path)
        return diff_out if diff_code == 0 else ""

    def diff_staged(self) -> str:
        code, stdout, stderr = self._run("diff", "--cached")
        return stdout if code == 0 else stderr

    def log(self, count: int = 10) -> list[dict]:
        code, stdout, _stderr = self._run(
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
                commits.append(
                    {
                        "hash": parts[0][:8],
                        "message": parts[1],
                        "author": parts[2],
                        "date": parts[3],
                    }
                )
        return commits
