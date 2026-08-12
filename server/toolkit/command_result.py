from __future__ import annotations

import re

from server.config.constants import BASH_FALSE_SUCCESS_PATTERNS

_FALSE_SUCCESS_RES = tuple(
    re.compile(re.escape(pattern), re.IGNORECASE) for pattern in BASH_FALSE_SUCCESS_PATTERNS
)


def detect_false_success(output: str, error: str) -> str | None:
    """Return a matched false-success signature, or ``None``.

    A shell command can exit 0 while never actually running (e.g. the Windows
    Store ``python`` alias prints "Unable to initialize device PRN" and does
    nothing). When a signature from ``BASH_FALSE_SUCCESS_PATTERNS`` appears in the
    combined output the result must be treated as a failure despite exit code 0.
    """
    combined = f"{output or ''}\n{error or ''}"
    for pattern, regex in zip(BASH_FALSE_SUCCESS_PATTERNS, _FALSE_SUCCESS_RES):
        if regex.search(combined):
            return pattern
    return None
