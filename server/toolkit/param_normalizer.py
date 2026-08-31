from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from server.toolkit.registry import ToolRegistry
except ImportError:  # pragma: no cover - for standalone use
    ToolRegistry = None


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


# --- Phase 1 additive: schema-based param decoding (module 23 / 03) ---
# opencode/codex decode tool params directly from JSON schema rather than
# a bespoke normalizer. This function uses the tool's declared schema to
# coerce/validate params, falling back to normalize_file_params for gaps.


def decode_params_with_schema(
    params: dict[str, Any],
    tool_name: str,
    tool_registry: ToolRegistry | None = None,
    workspace_root: str | None = None,
) -> dict[str, Any]:
    """Decode params using the tool's JSON schema, with fallback to legacy normalizer.

    This is the Phase 1 additive replacement for `normalize_file_params`.
    It uses the tool's declared schema to coerce types and validate required
    fields. Unknown keys are preserved (for forward compat). The legacy
    `normalize_file_params` is still applied for path canonicalization gaps.

    Returns the decoded params dict, or the original params on any error
    (never raises - the executor will catch validation failures downstream).
    """
    if tool_registry is None:
        return normalize_file_params(params, tool_name)

    tool = tool_registry.get(tool_name)
    if tool is None or not hasattr(tool, "schema"):
        return normalize_file_params(params, tool_name)

    schema = getattr(tool, "schema", None)
    if not isinstance(schema, dict):
        return normalize_file_params(params, tool_name)

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    # Start with legacy-normalized params (handles path canonicalization etc.)
    decoded = normalize_file_params(params, tool_name)

    # Coerce types per schema properties
    for key, value in decoded.items():
        prop_schema = properties.get(key)
        if not isinstance(prop_schema, dict):
            continue
        prop_type = prop_schema.get("type")
        if prop_type == "integer" and isinstance(value, str):
            try:
                decoded[key] = int(value)
            except ValueError:
                pass
        elif prop_type == "number" and isinstance(value, str):
            try:
                decoded[key] = float(value)
            except ValueError:
                pass
        elif prop_type == "boolean" and isinstance(value, str):
            decoded[key] = value.lower() in ("true", "1", "yes", "on")
        elif prop_type == "array" and isinstance(value, str):
            try:
                decoded[key] = json.loads(value)
            except json.JSONDecodeError:
                pass
        elif prop_type == "object" and isinstance(value, str):
            try:
                decoded[key] = json.loads(value)
            except json.JSONDecodeError:
                pass

    # Add missing required fields with defaults from schema
    for req_key in required:
        if req_key not in decoded:
            prop_schema = properties.get(req_key, {})
            default = prop_schema.get("default")
            if default is not None:
                decoded[req_key] = default

    return decoded
