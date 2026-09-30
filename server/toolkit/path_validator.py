from __future__ import annotations

import difflib
import enum
import platform
import re
from functools import lru_cache
from pathlib import Path

_WIN_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$", re.IGNORECASE)
_WIN_INVALID_CHARS = re.compile(r'[<>:"|?*\x00-\x1F]')

# Bounds for suggestion search. A miss must stay cheap enough to run on every
# failed path: the model may retry in a loop, and each attempt already pays for
# a round trip.
_MAX_SIBLINGS_SCANNED = 2000
_MAX_SUGGESTIONS = 3
_CLOSE_CUTOFF = 0.6
_NEAR_MISS_CUTOFF = 0.5


@lru_cache(maxsize=64)
def _resolved_workspace(workspace_root: str) -> Path:
    return Path(workspace_root).resolve()


class PathRejection(enum.Enum):
    """Why a path was refused. Each reason has its own recovery advice.

    Collapsing every refusal into one message told the model that a Windows
    name containing a colon "escaped the workspace", which is not what happened
    and not something the model can act on. The category is carried through so
    the caller can say what actually went wrong.
    """

    EMPTY = "empty"
    UNRESOLVABLE = "unresolvable"
    OUTSIDE_WORKSPACE = "outside_workspace"
    RESERVED_NAME = "reserved_name"
    INVALID_CHARACTER = "invalid_character"


_REJECTION_ADVICE: dict[PathRejection, str] = {
    PathRejection.EMPTY: "Provide a file path relative to the workspace root.",
    PathRejection.UNRESOLVABLE: (
        "The path could not be resolved on this filesystem. Check it for invalid "
        "characters and confirm the parent directory exists."
    ),
    PathRejection.OUTSIDE_WORKSPACE: (
        "Only paths inside the workspace can be touched. Use a path relative to "
        "the project root."
    ),
    PathRejection.RESERVED_NAME: (
        "That is a reserved device name on Windows (CON, PRN, AUX, NUL, COM1-9, "
        "LPT1-9). Rename the file."
    ),
    PathRejection.INVALID_CHARACTER: (
        "A Windows filename cannot contain < > : \" | ? * or control characters. "
        "Choose a different name."
    ),
}


def classify_path_rejection(rel_path: str, workspace_root: str) -> PathRejection | None:
    """Why ``rel_path`` is unusable, or ``None`` when it is fine."""
    if not rel_path:
        return PathRejection.EMPTY
    workspace = _resolved_workspace(workspace_root)
    try:
        resolved = (workspace / rel_path).resolve()
    except (OSError, ValueError):
        return PathRejection.UNRESOLVABLE
    try:
        resolved.relative_to(workspace)
    except ValueError:
        return PathRejection.OUTSIDE_WORKSPACE
    if platform.system() == "Windows":
        if _WIN_RESERVED.match(resolved.name):
            return PathRejection.RESERVED_NAME
        if _WIN_INVALID_CHARS.search(resolved.name):
            return PathRejection.INVALID_CHARACTER
    return None


def path_rejection_error(rel_path: str, workspace_root: str) -> str | None:
    """A message for a refused path, or ``None`` when the path is acceptable."""
    reason = classify_path_rejection(rel_path, workspace_root)
    if reason is None:
        return None
    if reason is PathRejection.EMPTY:
        return f"Missing file path parameter. {_REJECTION_ADVICE[reason]}"
    return (
        f"Path rejected: {rel_path} ({reason.value.replace('_', ' ')}). "
        f"{_REJECTION_ADVICE[reason]}"
    )


def validate_path(rel_path: str, workspace_root: str) -> Path | None:
    if not rel_path:
        return None
    workspace = _resolved_workspace(workspace_root)
    try:
        resolved = (workspace / rel_path).resolve()
    except (OSError, ValueError):
        return None
    try:
        resolved.relative_to(workspace)
    except ValueError:
        return None
    # Windows reserved name check (codex shell_spec.rs). The invalid-char
    # check targets the leaf name (e.g. "a<b>.txt"), not the full absolute
    # path which legitimately contains a drive colon and separators.
    if platform.system() == "Windows":
        if _WIN_RESERVED.match(resolved.name):
            return None
        if _WIN_INVALID_CHARS.search(resolved.name):
            return None
    return resolved


def _is_visible(rel_path: str, workspace_root: str) -> bool:
    """False when the ignore rules treat ``rel_path`` as nonexistent.

    Suggestions must not become a side channel. A path excluded by
    ``.zenithignore`` is reported as missing everywhere else precisely so the
    agent cannot learn that it exists; offering it back as a "did you mean"
    alternative would undo that, and would be a leak the caller has to remember
    to avoid at every call site.
    """
    try:
        from server.workspace.ignore import blocked_as_missing, get_matcher

        return not blocked_as_missing(get_matcher(workspace_root), rel_path)
    except Exception:
        # If the matcher cannot be built, show everything rather than silently
        # offering nothing.
        return True


def suggest_alternatives(rel_path: str, workspace_root: str) -> list[str]:
    """Closest existing paths to ``rel_path``, for a not-found error.

    "File not found: server/toolkit/file_reed.py" on its own gives the model
    nothing to act on: the correct spelling is inferable but not obvious, so
    the only recovery is another blind guess. Naming the near misses turns a
    retry loop into a single corrected call.

    Two cases are covered, because they fail for different reasons:

    * The parent directory exists — the filename is wrong. Siblings are
      compared by name, which catches a transposed, truncated, or wrong-suffix
      spelling.
    * The parent directory does not exist — the *directory* is wrong. The
      deepest existing ancestor is found, and its own siblings are compared
      against the first missing segment.

    Every suggestion is returned workspace-relative. An absolute path would
    echo the host's directory layout back to the model, which is both noise and
    a small information leak.
    """
    if not rel_path:
        return []
    workspace = _resolved_workspace(workspace_root)
    target = Path(rel_path)
    parent = workspace / target.parent if str(target.parent) else workspace

    # Climb to the deepest ancestor that actually exists.
    probe = parent
    while True:
        if probe.is_dir():
            break
        if probe == workspace or probe.parent == probe:
            return []
        probe = probe.parent
    if not probe.is_dir():
        return []

    try:
        missing = parent.relative_to(probe).parts
    except ValueError:
        return []
    wanted = missing[0] if missing else target.name

    try:
        entries = sorted(p.name for p in probe.iterdir())
    except OSError:
        return []
    if len(entries) > _MAX_SIBLINGS_SCANNED:
        entries = entries[:_MAX_SIBLINGS_SCANNED]

    close = difflib.get_close_matches(wanted, entries, n=_MAX_SUGGESTIONS, cutoff=_CLOSE_CUTOFF)
    if not close:
        close = difflib.get_close_matches(
            wanted, entries, n=_MAX_SUGGESTIONS, cutoff=_NEAR_MISS_CUTOFF
        )
    if not close:
        return []

    base = probe.relative_to(workspace).as_posix()
    prefix = "" if base in ("", ".") else f"{base}/"
    out: list[str] = []
    for name in close:
        candidate_rel = f"{prefix}{name}"
        if not _is_visible(candidate_rel, workspace_root):
            continue
        candidate = probe / name
        out.append(f"{candidate_rel}/" if candidate.is_dir() else candidate_rel)
    return out[:_MAX_SUGGESTIONS]


def not_found_error(rel_path: str, workspace_root: str) -> str:
    """A not-found message that carries its own recovery, when one exists."""
    message = f"File not found: {rel_path}"
    try:
        suggestions = suggest_alternatives(rel_path, workspace_root)
    except OSError:
        suggestions = []
    if suggestions:
        message += "\n\nDid you mean one of these?\n" + "\n".join(suggestions)
    return message
