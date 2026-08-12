from __future__ import annotations

import re
from pathlib import Path

from server.config.constants import DEFAULT_CONTEXT_WINDOW


def reflection_error_limit(context_window: int = DEFAULT_CONTEXT_WINDOW) -> int:
    if context_window <= 32000:
        return 3
    extra = (context_window - 32000) // 64000
    return min(3 + extra, 20)


_PLACEHOLDER_PATTERNS_RAW = [
    (
        "\\[[\\w\\s]*(?:CONTENT|FILE|CODE|PASTE|INSERT|TODO|DESIRED|UPDATED|REPLACE|YOUR)[\\w\\s]*\\]",
        "placeholder pattern",
    ),
    ("\\bYOUR_[\\w_]+_HERE\\b", "YOUR_..._HERE placeholder"),
    ("\\b(?:PLACEHOLDER|TODO|FIXME|XXX|TBD)\\b", "TODO/placeholder marker"),
    ("\\[HTML\\]", "HTML placeholder"),
    ("\\[ACTUAL_", "ACTUAL_ placeholder"),
    ("\\[Current ", "Current... placeholder"),
    ("\\[UPDATED_", "UPDATED_ placeholder"),
]
_PLACEHOLDER_RE = re.compile("|".join((p for p, _ in _PLACEHOLDER_PATTERNS_RAW)), re.IGNORECASE)
_INTERACTIVE_CMD_PATTERNS = re.compile(
    "\\binput\\s*\\(|python\\s+-i\\b|python\\s+-im\\b|python\\s+-mi\\b|\\bpdb\\b|\\bgetpass\\b|\\bread\\s+-[srp]\\b",
    re.IGNORECASE,
)
_CD_PREFIX_RE = re.compile(
    r"^(?:Set-Location|cd)\s+(?:\"([^\"]+)\"|'([^']+)'|([^;|&\"'\s]+))"
    r"\s*(?:;|&&|)\s*",
    re.IGNORECASE,
)


def detect_placeholders(params: dict) -> str | None:
    for key in ("content", "old_content", "new_content"):
        val = params.get(key, "")
        if isinstance(val, str) and val:
            m = _PLACEHOLDER_RE.search(val)
            if m:
                return f"Parameter '{key}' contains placeholder content ({m.group(0)}). Provide the actual content."
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


def parse_cd_prefix(command: str) -> tuple[str | None, str]:
    """Split a leading ``cd <dir>;`` / ``Set-Location <dir>;`` prefix off a command.

    Returns ``(target, remainder)`` where ``target`` is the directory the model
    asked to change into (with quotes stripped), or ``None`` when the command has
    no leading change-directory prefix. ``remainder`` is the rest of the command.
    The prefix is only split off when a usable target and a remainder both exist.
    """
    m = _CD_PREFIX_RE.match(command.strip())
    if not m:
        return None, command
    target = next((g for g in m.groups() if g), None)
    remainder = command.strip()[m.end() :].strip()
    if target is None or not remainder:
        return None, command
    return target, remainder


def strip_cd_prefix(command: str) -> str:
    """Return the command without its leading change-directory prefix."""
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
