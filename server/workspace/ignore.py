"""Single source of truth for workspace skipping: the ``.zenithignore`` file.

The file lives at the workspace root and uses gitignore syntax (handled by
``pathspec.GitIgnoreSpec``). Paths matched by it are treated as nonexistent by
every discovery and mutation tool — they are never listed, searched, read,
written, edited, or deleted.

Startup calls :func:`ensure_ignore_file` to seed the file from
``DEFAULT_ZENITH_IGNORE_CONTENT`` when missing. If the file cannot be created
(read-only workspace) the same template is applied in memory, so default
exclusions always hold. When the file exists its content is used exclusively;
edits take effect on the next tool call (mtime/size fingerprint reload).
"""

from __future__ import annotations
import logging
import threading
from pathlib import Path
from pathspec import GitIgnoreSpec
from server.config.constants import (
    DEFAULT_ZENITH_IGNORE_CONTENT,
    ZENITH_IGNORE_FILE_NAME,
)

logger = logging.getLogger(__name__)


def ignore_file_path(workspace_root: str | Path) -> Path:
    """Absolute path of the ignore file for a workspace."""
    return Path(workspace_root) / ZENITH_IGNORE_FILE_NAME


def ensure_ignore_file(workspace_root: str | Path) -> Path:
    """Create ``.zenithignore`` from the template if missing; return its path.

    Best-effort: failures are logged and never raised so startup and tests are
    unaffected when the target directory is read-only.
    """
    path = ignore_file_path(workspace_root)
    try:
        if not path.exists():
            path.write_text(DEFAULT_ZENITH_IGNORE_CONTENT, encoding="utf-8")
            logger.info("Created %s from default template", path)
    except OSError as e:
        logger.warning("Could not write %s: %s", path, e)
    return path


def _normalize_rel(rel_path: str | Path) -> str:
    text = str(rel_path).replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text.strip("/")


class ZenithIgnoreMatcher:
    """Gitignore-style matcher over ``<workspace>/.zenithignore``.

    Call :meth:`refresh` once per operation, then query any number of paths via
    :meth:`is_ignored` / :meth:`is_ignored_dir`. The ignore file itself is
    always exempt so users can edit their rules through Zenith tools.
    """

    def __init__(self, workspace_root: str | Path) -> None:
        self._file = ignore_file_path(workspace_root)
        self._fingerprint: tuple[int, int] | None = None
        self._spec: GitIgnoreSpec | None = None
        self._loaded = False
        self.refresh()

    def refresh(self) -> None:
        """Reload the spec when the underlying file changed or is unread."""
        try:
            stat = self._file.stat()
            fingerprint: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            fingerprint = None
        if self._loaded and fingerprint == self._fingerprint:
            return
        self._fingerprint = fingerprint
        if fingerprint is None:
            self._spec = GitIgnoreSpec.from_lines(DEFAULT_ZENITH_IGNORE_CONTENT.splitlines())
            logger.info("%s absent; applying default ignore template in memory", self._file)
        else:
            try:
                lines = self._file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError as e:
                logger.warning("Failed reading %s (%s); using defaults", self._file, e)
                lines = DEFAULT_ZENITH_IGNORE_CONTENT.splitlines()
            self._spec = GitIgnoreSpec.from_lines(lines)
        self._loaded = True

    def is_ignored(self, rel_path: str | Path) -> bool:
        """True when a workspace-relative file path must be skipped."""
        normalized = _normalize_rel(rel_path)
        if not normalized or normalized == ZENITH_IGNORE_FILE_NAME:
            return False
        assert self._spec is not None  # set by __init__/refresh
        return self._spec.match_file(normalized)

    def is_ignored_dir(self, rel_dir: str | Path) -> bool:
        """True when a workspace-relative directory must be pruned."""
        normalized = _normalize_rel(rel_dir)
        if not normalized or normalized == ZENITH_IGNORE_FILE_NAME:
            return False
        assert self._spec is not None
        return self._spec.match_file(normalized + "/")


_matchers: dict[str, ZenithIgnoreMatcher] = {}
_cache_lock = threading.Lock()


def get_matcher(workspace_root: str | Path) -> ZenithIgnoreMatcher:
    """Cached matcher for a workspace; one instance per resolved root."""
    key = str(Path(workspace_root).resolve())
    with _cache_lock:
        matcher = _matchers.get(key)
        if matcher is None:
            matcher = ZenithIgnoreMatcher(key)
            _matchers[key] = matcher
        return matcher


def blocked_as_missing(matcher: ZenithIgnoreMatcher, rel_path: str | Path) -> bool:
    """True when a read/write target must be reported as nonexistent.

    Ignored paths are invisible: callers return their standard not-found error
    so the agent cannot distinguish them from genuinely missing files. This is
    the only place the block is logged.
    """
    matcher.refresh()
    if matcher.is_ignored(rel_path) or matcher.is_ignored_dir(rel_path):
        logger.info("Ignored by .zenithignore; reporting as not found: %s", rel_path)
        return True
    return False
