from __future__ import annotations

import json
import logging
import re

from json_repair import repair_json

logger = logging.getLogger(__name__)
TOOL_PATTERNS = [
    re.compile(
        '```(?:tool|json)?\\s*\\n?(\\{[\\s\\S]*?\\"tool\\"\\s*:\\s*\\"[^\\"]+\\"[\\s\\S]*?\\})\\s*\\n?```',
        re.IGNORECASE,
    ),
    re.compile(
        '(\\{[\\s\\S]*?\\"tool\\"\\s*:\\s*\\"[^\\"]+\\"[\\s\\S]*?\\"params\\"\\s*:\\s*\\{[\\s\\S]*?\\}\\s*\\})'
    ),
]
XML_TOOL_CALL_PATTERN = re.compile(
    r"<tool_call>\s*([^<\s]+)([\s\S]*?)</tool_call>", re.IGNORECASE
)
XML_ARG_PATTERN = re.compile(
    r"<arg_key>(.*?)</arg_key>\s*<arg_value>(.*?)</arg_value>", re.IGNORECASE | re.DOTALL
)
PLACEHOLDER_TOOL_NAMES = frozenset(
    {"tool_name", "tool", "function", "name", "call", "action", "command", "method"}
)

_XML_CALL_CLEAN_RE = re.compile(r"<tool_call>[\s\S]*?</tool_call>", re.IGNORECASE)
_TOOL_FENCE_CLEAN_RE = re.compile(
    r'```(?:tool|json)?\s*\n?\{[\s\S]*?\"tool\"\s*:\s*\"[^\"]+\"[\s\S]*?\}\s*\n?```',
    re.IGNORECASE,
)
_TOOL_OBJECT_CLEAN_RE = re.compile(
    r'\{[\s\S]*?\"tool\"\s*:\s*\"[^\"]+\"[\s\S]*?\"params\"\s*:\s*\{[\s\S]*?\}\s*\}'
)
_SIMULATED_CMD_RE = re.compile(
    r"^Command:\s+.*$\n^Output:.*$", flags=re.MULTILINE | re.IGNORECASE
)
_SIMULATED_SUCCESS_RE = re.compile(
    r"^Successfully (?:created|wrote|deleted|edited) (?:new )?file:\s*[^\n]+$",
    flags=re.MULTILINE | re.IGNORECASE,
)
_PLACEHOLDER_MARKER_RE = re.compile(
    r"\[(?:PASTE|INSERT|TODO|HTML|UPDATED|ACTUAL|CURRENT|DESIRED)[^\]]{0,50}\]",
    flags=re.IGNORECASE,
)
_YOUR_PLACEHOLDER_RE = re.compile(r"\bYOUR_[\w_]+_HERE\b")
_EXTRA_NEWLINES_RE = re.compile(r"\n{3,}")


def _normalize_triple_quoted_strings(candidate: str) -> str:
    if '"""' not in candidate:
        return candidate

    def _replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}{json.dumps(match.group(2))}"

    return re.sub(r'(:\s*)"""([\s\S]*?)"""', _replace, candidate)


def _split_top_level_objects(text: str) -> list[str]:
    objects: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                objects.append(text[start : i + 1])
                start = -1
    return objects


def _repair_and_parse_json(candidate: str) -> dict | None:
    cleaned_cand = re.sub("^```(?:tool|json)?\\s*", "", candidate.strip(), flags=re.IGNORECASE)
    cleaned_cand = re.sub("\\s*```$", "", cleaned_cand).strip()
    cleaned_cand = _normalize_triple_quoted_strings(cleaned_cand)

    def _validate_tool_name(data: dict) -> dict | None:
        name = data.get("tool", "")
        if name in PLACEHOLDER_TOOL_NAMES:
            return None
        return data

    try:
        repaired = repair_json(cleaned_cand)
        data = json.loads(repaired)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if "function" in data and "tool" not in data:
        data["tool"] = data.pop("function")
    if "arguments" in data and "params" not in data:
        args = data.pop("arguments")
        data["params"] = args if isinstance(args, dict) else {}
    if "tool" not in data:
        return None
    if data.get("tool") in PLACEHOLDER_TOOL_NAMES:
        return None
    params = data.get("params")
    if params is None:
        data["params"] = {}
    elif not isinstance(params, dict):
        return None
    return _validate_tool_name(data)


def parse_tool_calls(text: str) -> list[dict]:
    from server.toolkit.param_normalizer import normalize_file_params

    calls: list[dict] = []
    seen: set[str] = set()
    matched_spans: list[tuple[int, int]] = []

    def _add_call(parsed: dict) -> bool:
        if not parsed or parsed.get("tool") in PLACEHOLDER_TOOL_NAMES:
            return False
        if "params" in parsed and isinstance(parsed["params"], dict):
            parsed["params"] = normalize_file_params(parsed["params"], parsed.get("tool"))
        sig = json.dumps(parsed, sort_keys=True)
        if sig in seen:
            return False
        calls.append(parsed)
        seen.add(sig)
        return True

    for pattern in TOOL_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any((s <= start and end <= e for s, e in matched_spans)):
                continue
            candidate = match.group(1) if len(match.groups()) > 0 else match.group(0)
            candidate = candidate.strip()
            if candidate.startswith("["):
                try:
                    arr = json.loads(candidate, strict=False)
                    if isinstance(arr, list):
                        added = False
                        for item in arr:
                            if isinstance(item, dict) and "tool" in item:
                                if "params" not in item:
                                    item["params"] = {}
                                if _add_call(item):
                                    added = True
                        if added:
                            matched_spans.append((start, end))
                        continue
                except Exception:
                    pass
            objects = _split_top_level_objects(candidate)
            if len(objects) > 1:
                added = False
                for obj in objects:
                    parsed = _repair_and_parse_json(obj)
                    if parsed and _add_call(parsed):
                        added = True
                if added:
                    matched_spans.append((start, end))
                continue
            parsed = _repair_and_parse_json(candidate)
            if parsed and _add_call(parsed):
                matched_spans.append((start, end))

    for match in XML_TOOL_CALL_PATTERN.finditer(text):
        start, end = match.span()
        if any((s <= start and end <= e for s, e in matched_spans)):
            continue
        tool = match.group(1).strip()
        if not tool or tool in PLACEHOLDER_TOOL_NAMES:
            continue
        params: dict[str, str] = {}
        for key, value in XML_ARG_PATTERN.findall(match.group(2)):
            params[key.strip()] = value
        if _add_call({"tool": tool, "params": params}):
            matched_spans.append((start, end))
    return calls


def clean_tool_text(text: str) -> str:
    cleaned = _XML_CALL_CLEAN_RE.sub("", text)
    cleaned = _TOOL_FENCE_CLEAN_RE.sub("", cleaned)
    cleaned = _TOOL_OBJECT_CLEAN_RE.sub("", cleaned)
    cleaned = _SIMULATED_CMD_RE.sub("", cleaned)
    cleaned = _SIMULATED_SUCCESS_RE.sub("", cleaned)
    cleaned = _PLACEHOLDER_MARKER_RE.sub("", cleaned)
    cleaned = _YOUR_PLACEHOLDER_RE.sub("", cleaned)
    cleaned = _EXTRA_NEWLINES_RE.sub("\n\n", cleaned)
    return cleaned.strip()


class UnifiedResponseFormatter:
    @staticmethod
    def process_response(
        raw_content: str, raw_tool_calls: list[dict] | None = None
    ) -> tuple[str, list[dict]]:
        tool_calls = []
        if raw_tool_calls:
            for tc in raw_tool_calls:
                remapped = UnifiedResponseFormatter._remap_native_tool_call(tc)
                if remapped:
                    tool_calls.append(remapped)
        if not tool_calls and raw_content.strip():
            tool_calls = parse_tool_calls(raw_content)
        clean_text = clean_tool_text(raw_content)
        return (clean_text, tool_calls)

    @staticmethod
    def _remap_native_tool_call(tc: dict) -> dict | None:
        from server.toolkit.param_normalizer import normalize_file_params

        if "function" in tc:
            func = tc["function"]
            name = func.get("name", "")
            if not name or name in PLACEHOLDER_TOOL_NAMES:
                return None
            args = func.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if not isinstance(args, dict):
                args = {}
            return {"tool": name, "params": normalize_file_params(args, name)}
        if "tool" in tc:
            params = tc.get("params", {})
            if not isinstance(params, dict):
                params = {}
            return {"tool": tc["tool"], "params": normalize_file_params(params, tc["tool"])}
        return None
