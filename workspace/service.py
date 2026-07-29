"""Workspace service — unified interface for git, files, repo map, and context files.

Aggregates the existing workspace modules (git, tracker, repo_map, context)
into a single service interface, adding:
- File history tracking
- Staleness detection
- Linter integration
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GitStatus:
    """Structured git status."""
    is_git_repo: bool
    branch: str = ""
    modified: list[str] = field(default_factory=list)
    staged: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    clean: bool = True
    error: str = ""


@dataclass
class GitCommit:
    """A single git commit."""
    hash: str
    message: str
    author: str
    date: str


@dataclass
class FileVersion:
    """A recorded version of a file."""
    path: str
    operation: str  # "created", "modified", "deleted"
    content: str
    timestamp: float


@dataclass
class LintResult:
    """Result of a lint operation."""
    file_path: str
    linter: str
    success: bool
    errors: list[dict[str, Any]] = field(default_factory=list)
    output: str = ""


class WorkspaceService:
    """Abstract workspace service interface."""

    @property
    def root(self) -> Path:
        ...

    async def get_git_status(self) -> GitStatus:
        ...

    async def get_diff(self, ref: str | None = None) -> str:
        ...

    async def get_log(self, limit: int = 10) -> list[GitCommit]:
        ...

    async def commit(self, message: str, files: list[str] | None = None) -> dict:
        ...

    def get_prompt_context(self) -> str:
        ...

    async def get_repo_map(self, max_tokens: int = 1000) -> str:
        ...

    def track_file(self, file_path: str, operation: str, content: str = "") -> None:
        ...

    def get_tracked_files(self) -> list[str]:
        ...

    def get_file_history(self, file_path: str) -> list[FileVersion]:
        ...

    def get_file_changes_summary(self) -> str:
        ...

    async def get_context_files(self) -> list[dict[str, str]]:
        ...

    async def run_linter(self, file_path: str, linter: str | None = None) -> LintResult:
        ...

    def is_gitignored(self, file_path: str) -> bool:
        ...


class DefaultWorkspaceService(WorkspaceService):
    """Workspace service backed by existing git, tracker, repo_map, context modules."""

    def __init__(self, workspace_root: str) -> None:
        self._root = Path(workspace_root).resolve()
        self._git = None
        self._tracker = None
        self._repo_map = None

    @property
    def root(self) -> Path:
        return self._root

    def _get_git(self):
        if self._git is None:
            from workspace.git import GitOps
            self._git = GitOps(str(self._root))
        return self._git

    def _get_tracker(self):
        if self._tracker is None:
            from workspace.tracker import FileTracker
            self._tracker = FileTracker(str(self._root))
        return self._tracker

    def _get_repo_map(self):
        if self._repo_map is None:
            from workspace.repo_map import RepoMap
            self._repo_map = RepoMap(str(self._root))
        return self._repo_map

    async def get_git_status(self) -> GitStatus:
        git = self._get_git()
        status = git.status()
        return GitStatus(
            is_git_repo=status.get("is_git_repo", False),
            branch=status.get("branch", ""),
            modified=status.get("modified", []),
            staged=status.get("staged", []),
            untracked=status.get("untracked", []),
            clean=status.get("clean", True),
            error=status.get("error", ""),
        )

    async def get_diff(self, ref: str | None = None) -> str:
        git = self._get_git()
        return git.diff(ref)

    async def get_log(self, limit: int = 10) -> list[GitCommit]:
        git = self._get_git()
        commits = git.log(count=limit)
        return [
            GitCommit(
                hash=c["hash"],
                message=c["message"],
                author=c["author"],
                date=c["date"],
            )
            for c in commits
        ]

    async def commit(self, message: str, files: list[str] | None = None) -> dict:
        git = self._get_git()
        return git.commit(message, files)

    def get_prompt_context(self) -> str:
        git = self._get_git()
        return git.get_prompt_context()

    async def get_repo_map(self, max_tokens: int = 1000) -> str:
        repo_map = self._get_repo_map()
        try:
            return repo_map.get_repo_map(max_tokens=max_tokens)
        except Exception as e:
            logger.warning("Repo map generation failed: %s", e)
            return ""

    def track_file(self, file_path: str, operation: str, content: str = "") -> None:
        tracker = self._get_tracker()
        tracker.track(file_path, operation, content)

    def get_tracked_files(self) -> list[str]:
        tracker = self._get_tracker()
        return tracker.get_changed_files()

    def get_file_history(self, file_path: str) -> list[FileVersion]:
        tracker = self._get_tracker()
        changes = tracker.get_changes()
        if file_path not in changes:
            return []
        info = changes[file_path]
        return [FileVersion(
            path=file_path,
            operation=info["operation"],
            content=info["content"],
            timestamp=info["timestamp"],
        )]

    def get_file_changes_summary(self) -> str:
        tracker = self._get_tracker()
        return tracker.get_summary()

    async def get_context_files(self) -> list[dict[str, str]]:
        from workspace.context import load_context_files
        files = load_context_files(str(self._root))
        return [{"path": f.path, "content": f.content, "scope": f.scope} for f in files]

    async def run_linter(self, file_path: str, linter: str | None = None) -> LintResult:
        from tools.auto_lint import run_lint
        try:
            result = await run_lint(file_path, str(self._root))
            return LintResult(
                file_path=file_path,
                linter=result.get("linter", linter or "unknown"),
                success=result.get("success", False),
                errors=result.get("errors", []),
                output=result.get("output", ""),
            )
        except Exception as e:
            return LintResult(
                file_path=file_path,
                linter=linter or "unknown",
                success=False,
                output=str(e),
            )

    def is_gitignored(self, file_path: str) -> bool:
        git = self._get_git()
        return git.is_gitignored(file_path)
