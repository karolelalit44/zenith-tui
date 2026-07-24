"""Parameter normalizer — canonicalizes LLM-generated tool param keys.

LLMs frequently hallucinate alternative parameter names (e.g. ``filename``
instead of ``path``, ``search`` instead of ``old_content``).  Normalizing
once at the boundary keeps every tool implementation clean.
"""

from __future__ import annotations

from typing import Any


# Canonical key ← set of known aliases (order matters: first match wins)
_PATH_ALIASES = ("filename", "file_path", "filepath", "file")
_OLD_CONTENT_ALIASES = ("search", "old_string", "find", "original")
_NEW_CONTENT_ALIASES = ("replace", "new_string", "replacement")


def normalize_file_params(params: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of *params* with aliased keys mapped to canonical names.

    Canonical keys produced:
    * ``path``         ← filename | file_path | filepath | file
    * ``old_content``  ← search | old_string | find | original
    * ``new_content``  ← replace | new_string | replacement
    """
    out = dict(params)

    # --- path ---
    if "path" not in out:
        for alias in _PATH_ALIASES:
            if alias in out:
                out["path"] = out.pop(alias)
                break

    # --- old_content ---
    if "old_content" not in out:
        for alias in _OLD_CONTENT_ALIASES:
            if alias in out:
                out["old_content"] = out.pop(alias)
                break

    # --- new_content ---
    if "new_content" not in out:
        for alias in _NEW_CONTENT_ALIASES:
            if alias in out:
                out["new_content"] = out.pop(alias)
                break

    return out
