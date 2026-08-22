from __future__ import annotations

_MAX_BRACE_EXPANSIONS = 64


def _split_top_level(body: str) -> list[str]:
    """Split a brace body on commas at nesting depth 0."""
    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(body):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(body[start:i])
            start = i + 1
    parts.append(body[start:])
    return parts


def _split_brace_group(pattern: str) -> tuple[str, list[str], str] | None:
    """Split the leftmost complete brace group into (prefix, options, suffix).

    Returns None when the pattern has no complete brace group (unbalanced
    braces included).
    """
    open_idx = pattern.find("{")
    if open_idx == -1:
        return None
    depth = 0
    for i in range(open_idx, len(pattern)):
        ch = pattern[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                body = pattern[open_idx + 1 : i]
                if not body:
                    return None
                options = _split_top_level(body)
                if len(options) <= 1:
                    return None
                return pattern[:open_idx], options, pattern[i + 1 :]
    return None


def expand_braces(pattern: str) -> list[str]:
    """Expand bash-style `{a,b}` brace groups into concrete glob patterns.

    Supports multiple and nested groups (cartesian product) and keeps result
    order stable. Patterns without braces (or with unbalanced braces) pass
    through unchanged as a single-element list. Expansion is capped to prevent
    combinatorial explosion; the original pattern is returned when the cap is
    exceeded.
    """
    patterns = [pattern]
    seen: set[str] = set()
    changed = True
    while changed:
        changed = False
        expanded: list[str] = []
        for p in patterns:
            group = _split_brace_group(p)
            if group is None:
                expanded.append(p)
                continue
            changed = True
            prefix, options, suffix = group
            expanded.extend(prefix + opt + suffix for opt in options)
        if len(expanded) > _MAX_BRACE_EXPANSIONS:
            return [pattern]
        patterns = expanded

    result: list[str] = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result
