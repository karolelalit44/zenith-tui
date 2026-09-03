from __future__ import annotations

from dataclasses import dataclass, field

# --- Phase 1 additive: consolidated execution result (module 23 / 05) ---
# Mirrors codex ExecResult (stdout/stderr/exit_code/error/truncated). Purely
# additive: this provides the richer result shape Phase 2 consumers (bash tool /
# executor) will use.


@dataclass
class CommandResult:
    """Consolidated result of a shell execution attempt.

    ``truncated`` records whether the captured output was budget-truncated
    (opencode/codex output-budget behaviour).
    """

    exit_code: int | None = None
    output: str = ""
    error: str = ""
    truncated: bool = False
    exception: str | None = None
    timed_out: bool = False
    _metadata: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True only if the command actually ran, completed, and exited 0."""
        if self.exit_code != 0:
            return False
        if self.exception is not None:
            return False
        return not self.timed_out

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
        return out
