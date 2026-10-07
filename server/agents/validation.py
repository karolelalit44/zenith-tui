from __future__ import annotations

import json
import logging
import re
import shlex
from pathlib import Path

from server.config.constants import DEFAULT_CONTEXT_WINDOW, SMALL_CONTEXT_WINDOW

logger = logging.getLogger(__name__)


def reflection_error_limit(context_window: int = DEFAULT_CONTEXT_WINDOW) -> int:
    if context_window <= SMALL_CONTEXT_WINDOW:
        return 3
    extra = (context_window - SMALL_CONTEXT_WINDOW) // 64000
    return min(3 + extra, 20)


_INTERACTIVE_CMD_PATTERNS = re.compile(
    "\\binput\\s*\\(|python\\s+-i\\b|python\\s+-im\\b|python\\s+-mi\\b|\\bpdb\\b|\\bgetpass\\b|\\bread\\s+-[srp]\\b",
    re.IGNORECASE,
)
_CD_PREFIX_RE = re.compile(
    r"^(?:Set-Location|cd)\s+(?:\"([^\"]+)\"|'([^']+)'|([^;|&\"'\s]+))"
    r"\s*(?:;|&&|)\s*",
    re.IGNORECASE,
)


_PLACEHOLDER_RE = re.compile(
    r"\b(?:YOUR_[A-Z0-9_]+_HERE|REPLACE_WITH_[A-Z0-9_]+|INSERT_[A-Z0-9_]+_HERE)\b"
    r"|\[[\w\s]*(?:INSERT|PASTE|REPLACE)[\w\s]+HERE\]"
    r"|\[ACTUAL_[A-Z0-9_]+\]"
    r"|\[YOUR_[A-Z0-9_]+\]",
    re.IGNORECASE,
)


def detect_placeholders(params: dict) -> str | None:
    for key in ("content", "old_content", "new_content"):
        val = params.get(key, "")
        if isinstance(val, str) and val:
            m = _PLACEHOLDER_RE.search(val)
            if m:
                return (
                    f"Parameter '{key}' contains template placeholder ({m.group(0)}). "
                    "Provide the actual implementation, not a placeholder."
                )
    return None


def check_python_syntax(command: str, workspace_root: str) -> str | None:
    m = re.match("^(?:python3?|py)\\s+([\\w./\\\\-]+\\.py)\\s*(.*)", command.strip(), re.IGNORECASE)
    if not m:
        return None
    filepath = m.group(1)
    full = Path(workspace_root) / filepath
    if not full.exists():
        return None
    try:
        import py_compile

        py_compile.compile(str(full), doraise=True)
    except py_compile.PyCompileError as e:
        return f"Python syntax error in {filepath}: {e}. Fix the syntax before running. Use file_read to check the file, then file_edit to fix it."
    return None


def detect_interactive_command(command: str) -> str | None:
    if _INTERACTIVE_CMD_PATTERNS.search(command):
        return "This command uses interactive input (input(), pdb, etc.) which will fail in non-interactive bash. Use echo 'value' | python script.py or rewrite the script to accept command-line arguments instead."
    return None


_VENV_DIR = ".venv"

# Interpreters that mean "the system Python" in a project that has its own venv.
# ``py`` is the Windows launcher; omitting it is why this guard was inert on
# Windows checkouts, where ``py -m pytest`` is the idiomatic invocation.
_SYSTEM_PYTHONS = {"python", "python3", "py"}
_PYTEST_SCRIPTS = {"pytest", "py.test"}


def _venv_python(workspace_root: str) -> str | None:
    """Path to the workspace virtualenv's interpreter, relative to the workspace.

    Derived rather than hardcoded: a venv lays its interpreter out as
    ``.venv/bin/python`` on POSIX and ``.venv\\Scripts\\python.exe`` on Windows, so
    a fixed POSIX path makes this check silently inert on every Windows
    checkout — the guard never fires and the message it would print names a file
    that is not there. Relative because the command runs with the workspace as
    its working directory.
    """
    root = Path(workspace_root) / _VENV_DIR
    candidates = (
        root / "Scripts" / "python.exe",
        root / "bin" / "python",
        root / "bin" / "python3",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate.relative_to(workspace_root).as_posix()
    return None


def _venv_activation_tokens(workspace_root: str) -> list[str]:
    """Every spelling of "activate this workspace venv" for the current layout.

    Derived next to the interpreter lookup so the accept-path and the
    correct-path cannot disagree about which platform they are on.
    """
    root = Path(workspace_root) / _VENV_DIR
    return [
        p.relative_to(workspace_root).as_posix()
        for p in (root / "Scripts" / "activate", root / "bin" / "activate")
        if p.exists()
    ]


def _split_command(command: str) -> list[str]:
    """Tokenize a command for policy inspection, never for execution.

    ``shlex`` is POSIX-only while the bash tool runs PowerShell on Windows, so a
    POSIX-only parse either fails or silently changes meaning. Fall back to
    whitespace splitting rather than pretending to understand PowerShell quoting.
    """
    try:
        return shlex.split(command.strip(), posix=True)
    except ValueError:
        logger.debug("shlex could not parse command; splitting on whitespace: %s", command)
        return command.strip().split()


def check_project_test_runner(command: str, workspace_root: str) -> str | None:
    venv_python = _venv_python(workspace_root)
    if venv_python is None:
        return None
    parts = _split_command(command)
    if not parts:
        return None
    # Already inside the workspace virtualenv: nothing to correct.
    if venv_python in command:
        return None
    if any(token in command for token in _venv_activation_tokens(workspace_root)):
        return None

    first = Path(parts[0]).name.lower()
    if first in _PYTEST_SCRIPTS:
        rest_parts = parts[1:]
    elif first in _SYSTEM_PYTHONS and parts[1:3] == ["-m", "pytest"]:
        rest_parts = parts[3:]
    else:
        return None
    rest = " ".join(shlex.quote(part) for part in rest_parts)
    suffix = f" {rest}" if rest else ""
    return f"Use the workspace virtualenv for pytest: {venv_python} -m pytest{suffix}"


# Generic names for an entrypoint that serves rather than runs and exits. Matched
# against the module's final segment and against a subcommand following ``-m``,
# so ``python -m http.server``, ``python -m myapp serve`` and
# ``python -m server.main serve`` are all caught without naming any one
# repository's module layout.
_LONG_RUNNING_ENTRYPOINTS = frozenset(
    {"http", "serve", "server", "runserver", "run", "asgi", "wsgi", "worker", "web"}
)

# Package managers whose script invocation names a script in a manifest.
_RUNNERS = {"npm": "run", "pnpm": "run", "yarn": ""}

# Binaries that are servers by construction: a script body that invokes one
# does not exit, whatever the script happens to be named.
_LONG_RUNNING_BINARIES = frozenset(
    {
        "vite",
        "next",
        "nuxt",
        "webpack-dev-server",
        "parcel",
        "uvicorn",
        "gunicorn",
        "hypercorn",
        "daphne",
        "http-server",
        "serve",
        "live-server",
        "nodemon",
        "concurrently",
        "watchexec",
        "pm2",
    }
)

# Substrings in a resolved script body that mean the process does not terminate.
_LONG_RUNNING_BODY_MARKERS = ("--watch", "-w ", " --host", "watch")


def _looks_long_running(script_body: str) -> bool:
    if any(marker in script_body for marker in _LONG_RUNNING_BODY_MARKERS):
        return True
    tokens = re.split(r"[\s;&|]+", script_body)
    return any(Path(token).name.lower() in _LONG_RUNNING_BINARIES for token in tokens)


def _manifest_scripts(manifest_dir: Path) -> dict[str, str]:
    """A package.json's script table, or an empty mapping if it is unusable."""
    try:
        data = json.loads((manifest_dir / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return {}
    return {str(k): str(v) for k, v in scripts.items()}


def _manifest_dir_for(parts: list[str], lowered: list[str], workspace_root: str) -> Path:
    """Where the runner will read package.json from."""
    manifest_dir = Path(workspace_root) if workspace_root else Path.cwd()
    for flag in ("--prefix", "-C", "--cwd"):
        if flag in lowered:
            idx = lowered.index(flag) + 1
            if idx < len(parts):
                candidate = Path(parts[idx])
                manifest_dir = candidate if candidate.is_absolute() else manifest_dir / candidate
    return manifest_dir


def check_long_running_dev_server(command: str, workspace_root: str = "") -> str | None:
    """Refuse to start a server that never exits, from inside an agent turn.

    The script name is resolved from the workspace manifest rather than matched
    against a list of common names. A name list misses ``start:api`` and
    ``dev:web`` while still refusing those same words in projects that never
    intended them as servers.
    """
    parts = _split_command(command)
    if not parts:
        return None
    lowered = [part.lower() for part in parts]
    head = Path(lowered[0]).name

    if head in _SYSTEM_PYTHONS and "-m" in lowered:
        idx = lowered.index("-m") + 1
        if idx >= len(lowered):
            return None
        module = lowered[idx]
        # The entrypoint may be named by the module (``http.server``) or by a
        # subcommand after it (``myapp serve``).
        candidates = [module.rsplit(".", 1)[-1], *lowered[idx + 1 :]]
        offending = next(
            (c for c in candidates if c.isalpha() and c in _LONG_RUNNING_ENTRYPOINTS), None
        )
        if offending:
            return (
                f"'{offending}' serves; it does not exit. Do not start servers inside "
                "an agent turn. Use the already-running external harness and inspect "
                "events, or run targeted tests instead."
            )
    if head in {"uvicorn", "gunicorn", "hypercorn", "celery", "vite", "next"}:
        return (
            f"'{head}' starts a long-lived process. Do not start it inside an agent "
            "turn. Inspect the already-running process or run targeted tests instead."
        )

    subcommand = _RUNNERS.get(head)
    if subcommand == "":
        script_idx = 1
    elif subcommand is not None:
        if subcommand not in lowered:
            return None
        script_idx = lowered.index(subcommand) + 1
    else:
        return None
    if script_idx >= len(parts):
        return None

    scripts = _manifest_scripts(_manifest_dir_for(parts, lowered, workspace_root))
    body = scripts.get(lowered[script_idx])
    if body is None or not _looks_long_running(body.lower()):
        return None
    return (
        f"'{lowered[script_idx]}' runs a long-lived process ({body}). Do not start it "
        "inside an agent turn. Inspect the already-running process or run targeted "
        "tests instead."
    )


def parse_cd_prefix(command: str) -> tuple[str | None, str]:
    m = _CD_PREFIX_RE.match(command.strip())
    if not m:
        return None, command
    target = next((g for g in m.groups() if g), None)
    remainder = command.strip()[m.end() :].strip()
    if target is None or not remainder:
        return None, command
    return target, remainder


def strip_cd_prefix(command: str) -> str:
    _, remainder = parse_cd_prefix(command)
    return remainder


def schemas_to_openai_tools(schemas: list[dict]) -> list[dict]:
    tools = []
    for s in schemas:
        schema = s.get("schema", {})
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": s["name"],
                    "description": s.get("description", ""),
                    "parameters": schema,
                },
            }
        )
    return tools
