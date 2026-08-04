"""Auto-lint — runs linters after file edits and returns diagnostics.

Detects file type from extension and runs the appropriate linter (ruff for
Python, eslint for JS/TS, etc.).  Returns lint results that can be fed back
to the agent as context for fixing issues.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class LintResult:
    """Result from running a linter on a file."""

    file_path: str
    linter: str
    success: bool
    output: str
    error_count: int = 0
    warning_count: int = 0


# Map of file extensions to linter commands
_LINTER_MAP: dict[str, tuple[str, str]] = {
    ".py": ("ruff", "check --output-format=concise"),
    ".js": ("eslint", "--no-error-on-unmatched-pattern"),
    ".jsx": ("eslint", "--no-error-on-unmatched-pattern"),
    ".ts": ("eslint", "--no-error-on-unmatched-pattern"),
    ".tsx": ("eslint", "--no-error-on-unmatched-pattern"),
}


def detect_linter(file_path: str) -> tuple[str, str] | None:
    """Detect the appropriate linter for a file based on its extension.

    Returns (linter_name, flags) or None if no linter is configured.
    """
    ext = Path(file_path).suffix.lower()
    return _LINTER_MAP.get(ext)


async def run_lint(file_path: str, workspace_root: str, timeout: int = 30) -> LintResult | None:
    """Run the appropriate linter on a file.

    Returns LintResult with diagnostics, or None if no linter is available.
    """
    linter_info = detect_linter(file_path)
    if not linter_info:
        return None

    linter_name, flags = linter_info
    rel_path = (
        str(Path(file_path).relative_to(workspace_root))
        if Path(file_path).is_absolute()
        else file_path
    )

    cmd = f"{linter_name} {flags} {rel_path}"
    logger.info("Auto-lint: %s", cmd)

    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace_root,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )
        output = stdout.decode("utf-8", errors="replace")
        error_output = stderr.decode("utf-8", errors="replace")
        exit_code = process.returncode

        # Parse error/warning counts from ruff output
        error_count = 0
        warning_count = 0
        if linter_name == "ruff":
            for line in output.split("\n"):
                if "error" in line.lower() and "found" in line.lower():
                    try:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == "error" and i > 0:
                                error_count = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
                elif "warning" in line.lower() and "found" in line.lower():
                    try:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == "warning" and i > 0:
                                warning_count = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass

        return LintResult(
            file_path=rel_path,
            linter=linter_name,
            success=exit_code == 0,
            output=output.strip() if output.strip() else error_output.strip(),
            error_count=error_count,
            warning_count=warning_count,
        )

    except TimeoutError:
        logger.warning("Auto-lint timed out for %s", file_path)
        return LintResult(
            file_path=rel_path,
            linter=linter_name,
            success=False,
            output=f"Lint timed out after {timeout}s",
        )
    except FileNotFoundError:
        logger.debug("Linter not found: %s", linter_name)
        return None
    except Exception as e:
        logger.debug("Auto-lint failed for %s: %s", file_path, e)
        return None


def format_lint_result(result: LintResult) -> str:
    """Format a lint result for feeding back to the agent."""
    if result.success and result.error_count == 0:
        return ""

    status = "PASSED" if result.success else "FAILED"
    parts = [f"[Lint {result.linter} | {status}] {result.file_path}"]

    if result.error_count:
        parts.append(f"  {result.error_count} error(s)")
    if result.warning_count:
        parts.append(f"  {result.warning_count} warning(s)")
    if result.output:
        # Truncate very long output
        output = result.output
        if len(output) > 2000:
            output = output[:2000] + "\n... (truncated)"
        parts.append(output)

    return "\n".join(parts)
