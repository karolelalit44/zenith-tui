"""Module 16 additive interface-lock: ripgrep-backed search primitive (glob/grep).

Reference: opencode tool/grep.ts calls ripgrep.grep; opencode tool/glob.ts calls ripgrep.glob.
zenith's existing grep.py / glob.py use ZenithIgnoreMatcher + pathspec; this additive module
provides a clean wrapper that (a) shells out to ``rg`` with native ignore-file support and
(b) returns a typed ``SearchMatch`` result compatible with the existing grep.py format.

The tree-sitter repo-map / code-graph stack is kept for Phase 3 coordinated removal;
this additive primitive is what the grep/glob tools will adopt in Phase 2.
"""

import asyncio
import functools
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

CmdRunner = Callable[[list[str]], Awaitable[tuple[int, str, str]]]


@dataclass(frozen=True)
class SearchMatch:
    """A grepped match, compatible with the format used by server/workspace/grep.py.

    Format: ``path:line:content`` where *content* is the line text.
    """

    path: str
    line_number: int | None = None
    text: str = ""


@functools.lru_cache(maxsize=1)
def _find_rg() -> str | None:
    """Locate the ``rg`` binary on PATH; cached for the process lifetime."""
    return shutil.which("rg")


async def _run(argv: list[str], cmd_runner: CmdRunner | None = None) -> tuple[int, str, str]:
    """Execute an ``rg`` command and return ``(returncode, stdout, stderr)``.

    If *cmd_runner* is supplied (used in tests), it is called instead of the real
    ``rg`` subprocess.  This makes the primitive testable without ``rg`` installed.
    """
    if cmd_runner is not None:
        return await cmd_runner(argv)
    rg = _find_rg()
    if rg is None:
        return 127, "", "rg binary not found on PATH"
    proc = await asyncio.create_subprocess_exec(
        rg, *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def _parse_grep_output(text: str) -> list[SearchMatch]:
    """Parse ``rg --line-number --no-heading --with-filename`` output into ``SearchMatch``.

    The emitted format is ``path:line:content``.  The path may itself contain colons
    (Windows drive letters) and the content may too, so scan from the right to find the
    *last* token that parses as an integer line number; everything before it is the path
    and everything after it is the content (both rejoined so embedded colons survive).
    """
    matches: list[SearchMatch] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(":")
        for i in range(len(parts) - 1, 0, -1):
            try:
                line_no = int(parts[i])
            except ValueError:
                continue
            matches.append(
                SearchMatch(
                    path=":".join(parts[:i]),
                    line_number=line_no,
                    text=":".join(parts[i + 1 :]),
                )
            )
            break
    return matches


class RipgrepBackend:
    """ripgrep-backed search primitive for glob/grep operations.

    Honours ``.gitignore`` natively and an extra ``.zenithignore`` file via ripgrep's
    ``--ignore-file`` flag.  The internal ``_cmd_runner`` hook makes it testable
    without ``rg`` installed.
    """

    def __init__(
        self,
        *,
        ignore_files: list[str] | None = None,
        max_results: int = 500,
        cmd_runner: CmdRunner | None = None,
    ) -> None:
        self.ignore_files: list[str] = list(ignore_files or [])
        self.max_results: int = max_results
        self._cmd_runner = cmd_runner

    async def _build_argv(
        self,
        *,
        pattern: str | None = None,
        include: str | None = None,
        files_only: bool = False,
        path: str | None = None,
    ) -> list[str]:
        """Assemble a ripgrep argv for either a content search or a file listing.

        Content search uses ``-e <pattern>`` and, when *include* is given, adds a
        ``--glob <include>`` *filter* (the pattern is still searched; include only
        narrows which files are examined).  File listing uses ``--files`` plus
        ``--glob <pattern>``.  ``.gitignore`` is honoured automatically; each extra
        ``--ignore-file`` is appended explicitly.
        """
        argv: list[str] = []
        if files_only:
            argv.append("--files")
            if pattern:
                argv.extend(["--glob", pattern])
            argv.append("--color")
            argv.append("never")
        else:
            if pattern is None:
                raise ValueError("pattern is required for a content search")
            argv.extend(["-e", pattern])
            if include:
                argv.extend(["--glob", include])
            argv.extend(
                [
                    "--max-count",
                    str(self.max_results),
                    "--no-heading",
                    "--with-filename",
                    "--line-number",
                    "--color",
                    "never",
                ]
            )
        for f in self.ignore_files:
            argv.extend(["--ignore-file", f])
        if path:
            argv.append(path)
        return argv

    async def grep(
        self, pattern: str, path: str, include: str | None = None
    ) -> list[SearchMatch]:
        """Search *pattern* under *path* and return line-level matches.

        *include* is a ripgrep glob (e.g. ``"*.py"``) that *filters which files are
        searched* while still matching *pattern* — matching opencode's grep semantics
        rather than replacing the pattern.
        """
        argv = await self._build_argv(pattern=pattern, include=include, path=path)
        code, out, _ = await _run(argv, self._cmd_runner)
        # ripgrep returns a non-zero (1) code when nothing matches; that is not an error.
        if code not in (0, 1) and not out.strip():
            return []
        return _parse_grep_output(out)[: self.max_results]

    async def glob(self, pattern: str, path: str) -> list[str]:
        """Return file paths under *path* matching *pattern* (ripgrep ``--files`` mode)."""
        argv = await self._build_argv(pattern=pattern, files_only=True, path=path)
        code, out, _ = await _run(argv, self._cmd_runner)
        if code not in (0, 1):
            return []
        return [ln for ln in out.splitlines() if ln.strip()][: self.max_results]


# Module-level default backend; other modules may import ``search`` and use the
# default instance, or construct their own with custom ``ignore_files`` / ``cmd_runner``.
DEFAULT_BACKEND: RipgrepBackend = RipgrepBackend()


__all__ = ["DEFAULT_BACKEND", "RipgrepBackend", "SearchMatch"]
