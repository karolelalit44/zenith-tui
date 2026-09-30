"""Failure classification for tool operations.

A tool that fails with ``str(exc)`` hands the model a raw operating-system
string. ``[WinError 32] The process cannot access the file because it is being
used by another process`` names a symptom in the platform's vocabulary, states
no cause the model can act on, and offers no recovery. The model's only options
are to give up or to repeat the identical call, and the second one produces the
identical string, so a single unhandled condition can stall a turn.

Every failure a file operation can hit is therefore classified into a category
with a fixed human description and a recovery instruction that depends on
whether retrying can possibly help. The contract is that a model reading a tool
error always learns three things: what happened, whether a retry is worth
attempting, and what to do instead if it is not.
"""

from __future__ import annotations

import errno
import os
from typing import Final

# Categories. These strings are stable and safe to surface to the model; they
# describe the class of failure, never the internals of the host.
NOT_FOUND: Final = "not_found"
PERMISSION: Final = "permission"
LOCKED: Final = "locked"
READ_ONLY: Final = "read_only"
IS_DIRECTORY: Final = "is_directory"
NOT_DIRECTORY: Final = "not_directory"
NO_SPACE: Final = "no_space"
ENCODING: Final = "encoding"
IS_BINARY: Final = "is_binary"
CONFLICT: Final = "conflict"
TIMEOUT: Final = "timeout"
IO_ERROR: Final = "io_error"

# errno -> category for POSIX hosts.
_ERRNO_CATEGORY: Final[dict[int, str]] = {
    errno.ENOENT: NOT_FOUND,
    errno.EACCES: PERMISSION,
    errno.EPERM: PERMISSION,
    errno.EROFS: READ_ONLY,
    errno.EISDIR: IS_DIRECTORY,
    errno.ENOTDIR: NOT_DIRECTORY,
    errno.ENOSPC: NO_SPACE,
    errno.EDQUOT: NO_SPACE,
    errno.ETXTBSY: LOCKED,
    errno.EBUSY: LOCKED,
}

# winerror -> category for Windows hosts.
_WINERROR_CATEGORY: Final[dict[int, str]] = {
    2: NOT_FOUND,  # ERROR_FILE_NOT_FOUND
    3: NOT_FOUND,  # ERROR_PATH_NOT_FOUND
    5: PERMISSION,  # ERROR_ACCESS_DENIED
    19: READ_ONLY,  # ERROR_WRITE_PROTECT
    21: IS_DIRECTORY,  # ERROR_IS_A_DIRECTORY
    32: LOCKED,  # ERROR_SHARING_VIOLATION
    33: LOCKED,  # ERROR_LOCK_VIOLATION
    39: NOT_DIRECTORY,  # ERROR_DIRECTORY
    112: NO_SPACE,  # ERROR_DISK_FULL
}

_RECOVERY: Final[dict[str, str]] = {
    NOT_FOUND: (
        "The path does not exist. Re-check the spelling, or list the parent "
        "directory to see what is actually there."
    ),
    PERMISSION: (
        "Access was denied by the filesystem. This will not succeed on retry. "
        "The file may be owned by another user or protected by the OS; choose a "
        "different location, or report it to the user."
    ),
    LOCKED: (
        "Another process is holding the file open. Retrying immediately will "
        "fail the same way. Wait for the other process to release it, or write "
        "to a different file."
    ),
    READ_ONLY: (
        "The location is read-only. Retrying cannot help. Write elsewhere and "
        "report the constraint to the user."
    ),
    IS_DIRECTORY: (
        "The path is a directory, not a file. Use list_dir to inspect it, or "
        "pass a path inside it."
    ),
    NOT_DIRECTORY: (
        "A path component is a file, not a directory. The target cannot exist "
        "at this path; choose a different location."
    ),
    NO_SPACE: (
        "The volume is out of space. Retrying will not help until space is "
        "freed; report this to the user."
    ),
    ENCODING: (
        "The file is not valid UTF-8 text. It is refused rather than rewritten, "
        "so no bytes were lost. Re-encode it to UTF-8 first, or operate on it "
        "with a tool that preserves its encoding."
    ),
    CONFLICT: (
        "The file changed on disk since it was read. Re-read it to obtain the "
        "current content, then reapply the change."
    ),
    TIMEOUT: "The operation exceeded its time budget and was stopped.",
    IO_ERROR: (
        "The filesystem operation failed. Re-reading the file will show "
        "whether it landed; retry only if the state is unclear."
    ),
}

# Past-tense description per category, used to build the leading clause.
_DESCRIPTION: Final[dict[str, str]] = {
    NOT_FOUND: "path does not exist",
    PERMISSION: "permission denied by the filesystem",
    LOCKED: "file is locked by another process",
    READ_ONLY: "location is read-only",
    IS_DIRECTORY: "path is a directory, not a file",
    NOT_DIRECTORY: "path component is not a directory",
    NO_SPACE: "no space left on the volume",
    ENCODING: "file is not valid UTF-8 text",
    IS_BINARY: "file is binary, not text",
    CONFLICT: "file changed on disk since it was read",
    TIMEOUT: "operation timed out",
    IO_ERROR: "filesystem operation failed",
}


def classify(exc: BaseException) -> str:
    """Map an exception to one of the stable failure categories.

    The errno/Windows-error tables are consulted *before* the exception-type
    checks, because Python derives the type from the errno: a Windows sharing
    violation arrives as errno 13 with ``winerror=32``, which the interpreter
    instantiates as ``PermissionError``. Testing the type first would therefore
    report a file that is merely open in another editor as a permission
    problem, and send the model to change ownership or pick a different
    directory — which is the wrong move entirely, since the file becomes
    writable the moment the other process closes it.
    """
    if isinstance(exc, UnicodeDecodeError | UnicodeEncodeError):
        return ENCODING
    if isinstance(exc, TimeoutError):
        return TIMEOUT
    if isinstance(exc, OSError):
        win_error = getattr(exc, "winerror", None)
        if isinstance(win_error, int) and win_error in _WINERROR_CATEGORY:
            return _WINERROR_CATEGORY[win_error]
        if exc.errno in _ERRNO_CATEGORY:
            return _ERRNO_CATEGORY[exc.errno]
        # Unmapped errno: fall back to the type Python derived from it.
        if isinstance(exc, IsADirectoryError):
            return IS_DIRECTORY
        if isinstance(exc, NotADirectoryError):
            return NOT_DIRECTORY
        if isinstance(exc, FileNotFoundError):
            return NOT_FOUND
        if isinstance(exc, PermissionError):
            return PERMISSION
        return IO_ERROR
    return IO_ERROR


def describe(exc: BaseException, *, action: str, path: str | None = None) -> str:
    """Render a classified, recoverable message for ``exc``.

    ``action`` is the operation in the model's own vocabulary ("read", "write",
    "delete", "patch", "create"). The leading clause names the category in
    plain language and the trailing clause says what to do, so the message is
    actionable without the model needing to decode an errno.
    """
    category = classify(exc)
    target = f" '{path}'" if path else ""
    return (
        f"Failed to {action}{target}: {_DESCRIPTION.get(category, category)}. "
        f"{_RECOVERY.get(category, _RECOVERY[IO_ERROR])}"
    )


def conflict_error(path: str) -> str:
    """Message for an optimistic-concurrency miss."""
    return f"Failed to write '{path}': {_DESCRIPTION[CONFLICT]}. {_RECOVERY[CONFLICT]}"


def is_read_only(exc: BaseException) -> bool:
    return classify(exc) == READ_ONLY


def is_permission(exc: BaseException) -> bool:
    return classify(exc) in (PERMISSION, READ_ONLY)


def errno_of(exc: BaseException) -> int | None:
    return exc.errno if isinstance(exc, OSError) else None


def errno_name(code: int) -> str:
    return os.strerror(code) if code else ""
