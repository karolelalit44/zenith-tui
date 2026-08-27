from __future__ import annotations

from pathlib import Path
from typing import Any


def _strip_key(key: str) -> str:
    return key.lower().replace("_", "").replace("-", "")


_PATH_CANONICAL_ALIASES = {
    "path",
    "filepath",
    "filename",
    "file",
    "targetfile",
    "targetpath",
    "dest",
    "destination",
    "outputfile",
    "outputpath",
    "pathname",
    "relpath",
    "absolutepath",
    "src",
    "source",
    "sourcefile",
}
_OLD_CONTENT_CANONICAL_ALIASES = {
    "search",
    "oldstring",
    "find",
    "original",
    "oldcontent",
    "targetcontent",
    "oldtext",
    "targettext",
}
_NEW_CONTENT_CANONICAL_ALIASES = {
    "replace",
    "newstring",
    "replacement",
    "newcontent",
    "replacementcontent",
    "newtext",
    "replacementtext",
}
_COMMAND_CANONICAL_ALIASES = {"command", "cmd", "commandstring", "script", "exec", "run"}
_PATTERN_CANONICAL_ALIASES = {"pattern", "query", "glob", "searchpattern", "filter", "regex"}

# Tools whose schema declares the path parameter as "filepath" (not "path").
_FILEPATH_KEY_TOOLS = {
    "multi_edit",
    "lsp_definition",
    "lsp_diagnostics",
    "lsp_rename",
}


def normalize_file_params(params: dict[str, Any], tool_name: str | None = None) -> dict[str, Any]:
    out = dict(params)

    def _apply_canonical(canonical: str, target_aliases: set[str]) -> None:
        if canonical in out:
            return
        for key in list(out.keys()):
            if _strip_key(key) in target_aliases:
                out[canonical] = out.pop(key)
                break

    path_canonical = "filepath" if tool_name in _FILEPATH_KEY_TOOLS else "path"
    _apply_canonical(path_canonical, _PATH_CANONICAL_ALIASES)
    _apply_canonical("old_content", _OLD_CONTENT_CANONICAL_ALIASES)
    _apply_canonical("new_content", _NEW_CONTENT_CANONICAL_ALIASES)
    _apply_canonical("command", _COMMAND_CANONICAL_ALIASES)
    _apply_canonical("pattern", _PATTERN_CANONICAL_ALIASES)
    for field in ("content", "old_content", "new_content"):
        if field in out:
            val = out[field]
            if isinstance(val, list):
                out[field] = "\n".join(str(item) for item in val)
            elif not isinstance(val, str) and val is not None:
                out[field] = str(val)
    return out


# Flags marking a path value that resolved to no canonical form.
_LITERAL_PATH_KEYS = ("path", "filepath", "pattern", "query", "glob")
_INVALID_PATH_PREFIX = "\0nopath:"
_ABS_PATH_PREFIX = "\0abs:"


def _is_path_key(key: str) -> bool:
    base = key.lstrip("_").lower()
    return base in _PATH_CANONICAL_ALIASES or base in _LITERAL_PATH_KEYS


def canonicalize_path_values(
    params: dict[str, Any], workspace_root: str | None = None
) -> dict[str, Any]:
    """Resolve path-valued params against ``workspace_root`` into stable identities.

    Equivalent spellings of the same file — ``sessions.py``, ``./sessions.py`` and
    ``<workspace>/sessions.py`` — must produce the same canonical value so the
    call signature treats them as the same call (dedup + loop detection). Only
    values whose key is an established path/pattern key are touched; all other
    parameters pass through untouched.

    Invalid or out-of-workspace paths keep a stable, distinct marker so they do
    NOT collide with each other or with a valid path.
    """
    if not workspace_root:
        return params
    workspace = Path(workspace_root).resolve()
    out = dict(params)
    for key in list(out.keys()):
        if not _is_path_key(key):
            continue
        value = out[key]
        if not isinstance(value, str) or not value.strip():
            continue
        candidate = value.strip()
        try:
            path = Path(candidate)
            # Absolute spellings are resolved as-is; relative spellings are
            # resolved against the workspace root. Both converge on the same
            # canonical identity so dedup/loop detection see one call.
            resolved = path if path.is_absolute() else workspace / path
            resolved = resolved.resolve()
            resolved.relative_to(workspace)
            out[key] = _ABS_PATH_PREFIX + str(resolved)
        except (OSError, ValueError):
            # Not a workspace-contained path. Keep it distinct and quotable so a
            # relative spelling and an escaping spelling can never collide.
            out[key] = _INVALID_PATH_PREFIX + candidate
    return out
