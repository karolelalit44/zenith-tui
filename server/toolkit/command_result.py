from __future__ import annotations

import re
from dataclasses import dataclass, field

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


# --- Phase 1 additive: consolidated execution result (module 23 / 05) ---
# Mirrors codex ExecResult (stdout/stderr/exit_code/error/truncated). Purely
# additive: detect_false_success stays for existing callers; this provides the
# richer result shape Phase 2 consumers (bash tool / executor) will use.


@dataclass
class CommandResult:
    """Consolidated result of a shell execution attempt.

    ``truncated`` records whether the captured output was budget-truncated
    (opencode/codex output-budget behaviour). ``false_success`` holds a matched
    BASH_FALSE_SUCCESS signature if one occurred, else ``None``.
    """

    exit_code: int | None = None
    output: str = ""
    error: str = ""
    truncated: bool = False
    false_success: str | None = None
    exception: str | None = None
    timed_out: bool = False
    _metadata: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True only if the command actually ran and exited 0.

        Exit 0 with a false-success signature (or a thrown exception) is NOT ok.
        """
        if self.exit_code != 0:
            return False
        if self.exception is not None:
            return False
        if self.timed_out:
            return False
        if self.false_success is not None:
            return False
        return True

    @property
    def combined(self) -> str:
        return f"{self.output or ''}\n{self.error or ''}".strip()

    @classmethod
    def from_parts(
        cls,
        *,
        exit_code: int | None,
        output: str,
        error: str,
        truncated: bool = False,
        trim_budget: int | None = None,
    ) -> CommandResult:
        """Build a CommandResult, applying an optional output truncation budget.

        When ``trim_budget`` is set and the combined output exceeds it, the
        stored output is trimmed to the budget and ``truncated`` is set True.
        """
        combined = f"{output or ''}\n{error or ''}"
        out = cls(exit_code=exit_code, output=output, error=error)
        if trim_budget and len(combined) > trim_budget:
            out.output = combined[:trim_budget]
            out.error = ""
            out.truncated = True
        out.false_success = detect_false_success(out.output, out.error)
        return out
