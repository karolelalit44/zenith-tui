"""Validation — tool parameter checks, command safety, and pattern detection."""

from __future__ import annotations

import re
from pathlib import Path


REFLECTION_ERROR_LIMIT = 6

_PLACEHOLDER_PATTERNS_RAW = [
    (r"\[[\w\s]*(?:CONTENT|FILE|CODE|PASTE|INSERT|TODO|DESIRED|UPDATED|REPLACE|YOUR)[\w\s]*\]", "placeholder pattern"),
    (r"\bYOUR_[\w_]+_HERE\b", "YOUR_..._HERE placeholder"),
    (r"\b(?:PLACEHOLDER|TODO|FIXME|XXX|TBD)\b", "TODO/placeholder marker"),
    (r"\[HTML\]", "HTML placeholder"),
    (r"\[ACTUAL_", "ACTUAL_ placeholder"),
    (r"\[Current ", "Current... placeholder"),
    (r"\[UPDATED_", "UPDATED_ placeholder"),
]
_PLACEHOLDER_RE = re.compile("|".join(p for p, _ in _PLACEHOLDER_PATTERNS_RAW), re.IGNORECASE)

_COMPLETION_SIGNALS = re.compile(
    r"(?:task\s+(?:is\s+)?(?:complete|done|finished)|"
    r"everything\s+is\s+(?:set|ready|done|complete)|"
    r"all\s+(?:steps?\s+)?(?:are\s+)?(?:complete|done|finished)|"
    r"summary\s*:|here(?:'s|\s+is)\s+(?:a\s+)?(?:summary|what\s+i\s+did)|"
    r"in\s+summary|to\s+sum(?:marize|mary)|"
    r"the\s+(?:code|file|script)\s+has\s+been|"
    r"(?:created|written|generated|implemented)\s+(?:successfully|complete))",
    re.IGNORECASE,
)

_INTERACTIVE_CMD_PATTERNS = re.compile(
    r"\binput\s*\(|"
    r"python\s+-[im]|"
    r"\bpdb\b|"
    r"\bgetpass\b|"
    r"\bread\s+-[srp]\b",
    re.IGNORECASE,
)

_CD_PREFIX_RE = re.compile(
    r"^(?:cd\s+[\"']?[^\"';|&]+[\"']?\s*(?:&&\s*|;\s*|)\s*)",
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
    m = re.match(r"^(?:python3?|py)\s+([\w./\\-]+\.py)\s*(.*)", command.strip(), re.IGNORECASE)
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
        return (
            f"Python syntax error in {filepath}: {e}. "
            f"Fix the syntax before running. Use file_read to check the file, then file_edit to fix it."
        )
    return None


def detect_interactive_command(command: str) -> str | None:
    if _INTERACTIVE_CMD_PATTERNS.search(command):
        return (
            "This command uses interactive input (input(), pdb, etc.) which will fail "
            "in non-interactive bash. Use echo 'value' | python script.py or rewrite "
            "the script to accept command-line arguments instead."
        )
    return None


def strip_cd_prefix(command: str) -> str:
    m = _CD_PREFIX_RE.match(command.strip())
    if m:
        stripped = command.strip()[m.end():].strip()
        if stripped:
            return stripped
    return command


def schemas_to_openai_tools(schemas: list[dict]) -> list[dict]:
    tools = []
    for s in schemas:
        schema = s.get("schema", {})
        tools.append({
            "type": "function",
            "function": {
                "name": s["name"],
                "description": s.get("description", ""),
                "parameters": schema,
            }
        })
    return tools
