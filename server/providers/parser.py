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
    re.compile("```(?:tool|json)?\\s*\\n?(\\[[\\s\\S]*?\\])\\s*\\n?```", re.IGNORECASE),
    re.compile(
        '(\\[[\\s\\S]*?\\{[\\s\\S]*?\\"tool\\"\\s*:\\s*\\"[^\\"]+\\"[\\s\\S]*?\\}[\\s\\S]*?\\])'
    ),
]
UNCLOSED_PATTERN = re.compile(
    '```(?:tool|json)?\\s*\\n?(\\{[\\s\\S]*?\\"tool\\"\\s*:\\s*\\"[^\\"]+\\"[\\s\\S]*)$',
    re.IGNORECASE,
)
BRACKET_PATTERN = re.compile('\\[(\\w+)((?:\\s+\\w+=(?:\\"[^\\"]*\\"|\\S+))+\\s*)\\]')
BRACKET_KV_PATTERN = re.compile('(\\w+)=(?:"((?:[^"\\\\]|\\\\.)*)"|(\\S+))')
XML_TOOL_CALL_PATTERN = re.compile("<tool_call>([\\s\\S]*?)</tool_call>", re.IGNORECASE)
XML_ARG_PAIR_PATTERN = re.compile(
    "<arg_key>(.*?)</arg_key>\\s*<arg_value>(.*?)</arg_value>", re.DOTALL | re.IGNORECASE
)
PLACEHOLDER_TOOL_NAMES = frozenset(
    {"tool_name", "tool", "function", "name", "call", "action", "command", "method"}
)


def _extract_string_value(text: str, key: str) -> str | None:
    single_line = re.search(f'"{key}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"', text)
    if single_line:
        raw = single_line.group(1)
        end_pos = single_line.end()
        is_triple_quote = raw == "" and end_pos < len(text) and (text[end_pos : end_pos + 1] == '"')
        if "\n" not in raw and (not is_triple_quote):
            return raw.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
    multi_match = re.search(f'"{key}"\\s*:\\s*(.*)"\\s*\\}}\\s*\\}}', text, re.DOTALL)
    if multi_match:
        raw = multi_match.group(1)
        raw = raw.removeprefix('"')
        return raw.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
    multi_match2 = re.search(f'"{key}"\\s*:\\s*(.*)"\\s*\\}}', text, re.DOTALL)
    if multi_match2:
        raw = multi_match2.group(1)
        raw = raw.removeprefix('"')
        return raw.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
    return None


def _extract_param_fallback(
    candidate: str, key: str, aliases: list[str] | None = None
) -> str | None:
    result = _extract_string_value(candidate, key)
    if result is not None:
        return result
    for alias in aliases or []:
        result = _extract_string_value(candidate, alias)
        if result is not None:
            return result
    return None


def _repair_and_parse_json(candidate: str) -> dict | None:
    cleaned_cand = re.sub("^```(?:tool|json)?\\s*", "", candidate.strip(), flags=re.IGNORECASE)
    cleaned_cand = re.sub("\\s*```$", "", cleaned_cand).strip()

    def _validate_tool_name(data: dict) -> dict | None:
        name = data.get("tool", "")
        if name in PLACEHOLDER_TOOL_NAMES:
            return None
        return data

    def _remap_openai_format(data: dict) -> dict:
        if "function" in data and "tool" not in data:
            data["tool"] = data.pop("function")
        if "arguments" in data and "params" not in data:
            args = data.pop("arguments")
            data["params"] = args if isinstance(args, dict) else {}
        return data

    if '"function"' in cleaned_cand and '"tool"' not in cleaned_cand:
        cleaned_cand = re.sub('"function"\\s*:\\s*"([^"]+)"', '"tool": "\\1"', cleaned_cand)
    if '"arguments"' in cleaned_cand and '"params"' not in cleaned_cand:
        cleaned_cand = cleaned_cand.replace('"arguments"', '"params"')
    json_result = None
    try:
        repaired = repair_json(cleaned_cand)
        data = json.loads(repaired)
        if isinstance(data, dict):
            if "tool" in data and "params" in data:
                json_result = _validate_tool_name(data)
            if not json_result and ("function" in data or "arguments" in data):
                data = _remap_openai_format(data)
                if "tool" in data and "params" in data:
                    json_result = _validate_tool_name(data)
    except Exception:
        pass
    if json_result:
        params = json_result.get("params", {})
        content = params.get("content", "")
        if content or json_result["tool"] != "file_write":
            return json_result
    tool_match = re.search('"tool"\\s*:\\s*"([^"]+)"', candidate)
    if tool_match:
        tool_name = tool_match.group(1)
        if tool_name in PLACEHOLDER_TOOL_NAMES:
            return None
        params: dict = {}
        path_val = _extract_param_fallback(
            candidate,
            "path",
            [
                "filePath",
                "filepath",
                "file_path",
                "targetFile",
                "target_file",
                "filename",
                "file_name",
                "targetPath",
                "target_path",
                "dest",
                "destination",
                "src",
                "source",
            ],
        )
        if path_val is not None:
            params["path"] = path_val
        content_val = _extract_param_fallback(candidate, "content")
        if content_val is not None:
            params["content"] = content_val
        old_val = _extract_param_fallback(
            candidate,
            "old_content",
            ["oldContent", "search", "find", "old_string", "original", "oldtext", "targettext"],
        )
        if old_val is not None:
            params["old_content"] = old_val
        new_val = _extract_param_fallback(
            candidate,
            "new_content",
            ["newContent", "replace", "new_string", "replacement", "newtext", "replacementtext"],
        )
        if new_val is not None:
            params["new_content"] = new_val
        cmd_val = _extract_param_fallback(
            candidate, "command", ["cmd", "commandString", "script", "exec", "run"]
        )
        if cmd_val is not None:
            params["command"] = cmd_val
        pattern_val = _extract_param_fallback(
            candidate, "pattern", ["query", "glob", "searchPattern", "filter", "regex"]
        )
        if pattern_val is not None:
            params["pattern"] = pattern_val
        url_val = _extract_param_fallback(candidate, "url")
        if url_val is not None:
            params["url"] = url_val
        include_val = _extract_param_fallback(candidate, "include")
        if include_val is not None:
            params["include"] = include_val
        timeout_match = re.search('"timeout"\\s*:\\s*(\\d+)', candidate)
        if timeout_match:
            params["timeout"] = int(timeout_match.group(1))
        if tool_name:
            return {"tool": tool_name, "params": params}
    return None


def parse_tool_calls(text: str) -> list[dict]:
    from server.toolkit.param_normalizer import normalize_file_params

    calls: list[dict] = []
    seen: set[str] = set()
    matched_spans: list[tuple[int, int]] = []

    def _add_call(parsed: dict) -> bool:
        if not parsed or parsed.get("tool") in PLACEHOLDER_TOOL_NAMES:
            return False
        if "params" in parsed and isinstance(parsed["params"], dict):
            parsed["params"] = normalize_file_params(parsed["params"])
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
                        for item in arr:
                            if isinstance(item, dict) and "tool" in item:
                                if "params" not in item:
                                    item["params"] = {}
                                _add_call(item)
                        matched_spans.append((start, end))
                        continue
                except Exception:
                    pass
            parsed = _repair_and_parse_json(candidate)
            if parsed and _add_call(parsed):
                matched_spans.append((start, end))
    if not calls:
        match = UNCLOSED_PATTERN.search(text)
        if match:
            candidate = match.group(1).strip()
            parsed = _repair_and_parse_json(candidate)
            if parsed and _add_call(parsed):
                calls.append(parsed)
    if not calls:
        for match in BRACKET_PATTERN.finditer(text):
            tool_name = match.group(1)
            if tool_name in PLACEHOLDER_TOOL_NAMES:
                continue
            params = {}
            for kv in BRACKET_KV_PATTERN.finditer(match.group(2)):
                key = kv.group(1)
                val = kv.group(2) if kv.group(2) is not None else kv.group(3)
                params[key] = val
            parsed = {"tool": tool_name, "params": normalize_file_params(params)}
            _add_call(parsed)
    if not calls:
        for match in XML_TOOL_CALL_PATTERN.finditer(text):
            content = match.group(1).strip()
            if not content:
                continue
            parsed = _repair_and_parse_json(content)
            if parsed and _add_call(parsed):
                continue
            arg_key_pos = content.find("<arg_key>")
            if arg_key_pos >= 0:
                tool_name = content[:arg_key_pos].strip()
                params = {}
                for kv in XML_ARG_PAIR_PATTERN.finditer(content):
                    k = kv.group(1).strip()
                    v = kv.group(2).strip()
                    params[k] = v
                if tool_name and tool_name not in PLACEHOLDER_TOOL_NAMES:
                    parsed = {"tool": tool_name, "params": normalize_file_params(params)}
                    _add_call(parsed)
    return calls


def clean_tool_text(text: str) -> str:
    cleaned = re.sub("<tool_call>[\\s\\S]*?</tool_call>", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(
        '```(?:tool|json)?\\s*\\n?\\{[\\s\\S]*?\\"tool\\"\\s*:\\s*\\"[^\\"]+\\"[\\s\\S]*?\\}\\s*\\n?```',
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        '\\{[\\s\\S]*?\\"tool\\"\\s*:\\s*\\"[^\\"]+\\"[\\s\\S]*?\\"params\\"\\s*:\\s*\\{[\\s\\S]*?\\}\\s*\\}',
        "",
        cleaned,
    )
    cleaned = re.sub(
        '```(?:tool|json)?\\s*\\n?\\[[\\s\\S]*?\\"tool\\"\\s*:\\s*\\"[^\\"]+\\"[\\s\\S]*?\\]\\s*\\n?```',
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        '\\[[\\s\\S]*?\\{[\\s\\S]*?\\"tool\\"\\s*:\\s*\\"[^\\"]+\\"[\\s\\S]*?\\}[\\s\\S]*?\\]',
        "",
        cleaned,
    )
    cleaned = re.sub('\\[(\\w+)((?:\\s+\\w+=(?:\\"[^\\"]*\\"|\\S+))+\\s*)\\]', "", cleaned)
    cleaned = re.sub(
        "^Command:\\s+.*$\\n^Output:.*$", "", cleaned, flags=re.MULTILINE | re.IGNORECASE
    )
    cleaned = re.sub(
        "^Successfully (?:created|wrote|deleted|edited) (?:new )?file:\\s*[^\\n]+$",
        "",
        cleaned,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    cleaned = re.sub(
        "\\[(?:PASTE|INSERT|TODO|HTML|UPDATED|ACTUAL|CURRENT|DESIRED)[^\\]]{0,50}\\]",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub("\\bYOUR_[\\w_]+_HERE\\b", "", cleaned)
    cleaned = re.sub("\\n{3,}", "\n\n", cleaned)
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
            return {"tool": name, "params": args}
        if "tool" in tc:
            params = tc.get("params", {})
            if not isinstance(params, dict):
                params = {}
            return {"tool": tc["tool"], "params": params}
        return None
