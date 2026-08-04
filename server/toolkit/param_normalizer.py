from __future__ import annotations

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


def normalize_file_params(params: dict[str, Any]) -> dict[str, Any]:
    out = dict(params)

    def _apply_canonical(canonical: str, target_aliases: set[str]) -> None:
        if canonical in out:
            return
        for key in list(out.keys()):
            if _strip_key(key) in target_aliases:
                out[canonical] = out.pop(key)
                break

    _apply_canonical("path", _PATH_CANONICAL_ALIASES)
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
