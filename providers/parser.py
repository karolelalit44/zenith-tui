from __future__ import annotations

import json
import re
import logging

logger = logging.getLogger(__name__)

TOOL_PATTERNS = [
    # Fenced tool blocks: ```tool\n{"tool":"..."}\n```
    re.compile(r"```(?:tool|json)?\s*\n?(\{[\s\S]*?\"tool\"\s*:\s*\"[^\"]+\"[\s\S]*?\})\s*\n?```", re.IGNORECASE),
    # Inline tool JSON: {"tool":"...", "params":{...}}
    re.compile(r"(\{[\s\S]*?\"tool\"\s*:\s*\"[^\"]+\"[\s\S]*?\"params\"\s*:\s*\{[\s\S]*?\}\s*\})"),
    # JSON array of tool calls: [{"tool":"...",...}, {"tool":"...",...}]
    re.compile(r"```(?:tool|json)?\s*\n?(\[[\s\S]*?\])\s*\n?```", re.IGNORECASE),
    # Inline JSON array (no fence)
    re.compile(r"(\[[\s\S]*?\{[\s\S]*?\"tool\"\s*:\s*\"[^\"]+\"[\s\S]*?\}[\s\S]*?\])"),
]

UNCLOSED_PATTERN = re.compile(r"```(?:tool|json)?\s*\n?(\{[\s\S]*?\"tool\"\s*:\s*\"[^\"]+\"[\s\S]*)$", re.IGNORECASE)

# Tool names that are placeholders the model might echo literally
PLACEHOLDER_TOOL_NAMES = frozenset({"tool_name", "tool", "function", "name", "call", "action", "command", "method"})


def _extract_string_value(text: str, key: str) -> str | None:
    """Extract a string value for a JSON key, handling escaped quotes and newlines."""
    # Try simple single-line match first (no actual newlines in value)
    single_line = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if single_line:
        raw = single_line.group(1)
        end_pos = single_line.end()
        # Reject empty matches that are actually start of triple-quoted content (""")
        is_triple_quote = raw == '' and end_pos < len(text) and text[end_pos:end_pos + 1] == '"'
        if '\n' not in raw and not is_triple_quote:
            return raw.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')

    # Try multi-line match: content may contain actual newlines.
    # Use greedy .* to find the LAST closing " before closing braces.
    # This handles triple-quoted strings (""") and content with embedded quotes.
    multi_match = re.search(rf'"{key}"\s*:\s*(.*)"\s*\}}\s*\}}', text, re.DOTALL)
    if multi_match:
        raw = multi_match.group(1)
        if raw.startswith('"'):
            raw = raw[1:]
        return raw.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')

    # Fallback: content followed by single closing brace (e.g., at end of params)
    multi_match2 = re.search(rf'"{key}"\s*:\s*(.*)"\s*\}}', text, re.DOTALL)
    if multi_match2:
        raw = multi_match2.group(1)
        if raw.startswith('"'):
            raw = raw[1:]
        return raw.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')

    return None


def _extract_param_fallback(candidate: str, key: str, aliases: list[str] | None = None) -> str | None:
    """Extract a parameter value by key name or alias variants."""
    result = _extract_string_value(candidate, key)
    if result is not None:
        return result
    for alias in (aliases or []):
        result = _extract_string_value(candidate, alias)
        if result is not None:
            return result
    return None


def _repair_and_parse_json(candidate: str) -> dict | None:
    """Repair dirty/unclosed JSON emitted by LLMs (e.g. unescaped newlines/quotes) and parse to dict."""
    cleaned_cand = re.sub(r"^```(?:tool|json)?\s*", "", candidate.strip(), flags=re.IGNORECASE)
    cleaned_cand = re.sub(r"\s*```$", "", cleaned_cand).strip()

    def _validate_tool_name(data: dict) -> dict | None:
        """Reject placeholder tool names the model might echo literally."""
        name = data.get("tool", "")
        if name in PLACEHOLDER_TOOL_NAMES:
            return None
        return data

    def _remap_openai_format(data: dict) -> dict:
        """Remap OpenAI 'function'+'arguments' to 'tool'+'params'."""
        if "function" in data and "tool" not in data:
            data["tool"] = data.pop("function")
        if "arguments" in data and "params" not in data:
            args = data.pop("arguments")
            data["params"] = args if isinstance(args, dict) else {}
        return data

    # 0. Pre-process: remap OpenAI format before parsing
    remapped = cleaned_cand
    if '"function"' in remapped and '"tool"' not in remapped:
        remapped = re.sub(r'"function"\s*:\s*"([^"]+)"', r'"tool": "\1"', remapped)
    if '"arguments"' in remapped and '"params"' not in remapped:
        remapped = remapped.replace('"arguments"', '"params"')

    # 1. Standard json.loads (non-strict allows control chars)
    try:
        data = json.loads(remapped, strict=False)
        if isinstance(data, dict) and "tool" in data and "params" in data:
            return _validate_tool_name(data)
        # Also handle OpenAI format after parse
        if isinstance(data, dict) and ("function" in data or "arguments" in data):
            data = _remap_openai_format(data)
            if "tool" in data and "params" in data:
                return _validate_tool_name(data)
    except Exception:
        pass

    # 2. Repair unclosed quotes and braces at end of truncated stream
    repaired_stream = cleaned_cand
    if repaired_stream.count('"') % 2 != 0:
        repaired_stream += '"'
    open_braces = repaired_stream.count('{') - repaired_stream.count('}')
    if open_braces > 0:
        repaired_stream += '}' * open_braces
    try:
        data = json.loads(repaired_stream, strict=False)
        if isinstance(data, dict) and "tool" in data:
            if "params" not in data:
                data["params"] = {}
            return _validate_tool_name(data)
    except Exception:
        pass

    # 3. Fix invalid backslash escapes (Windows paths like \v, \c)
    sanitized = re.sub(r'\\(?![\\"/bfnrtu])', '/', cleaned_cand)
    try:
        data = json.loads(sanitized, strict=False)
        if isinstance(data, dict) and "tool" in data and "params" in data:
            return _validate_tool_name(data)
    except Exception:
        pass

    # 4. Handle trailing commas before closing braces
    fixed_commas = re.sub(r",\s*([\}\]])", r"\1", sanitized)
    try:
        data = json.loads(fixed_commas, strict=False)
        if isinstance(data, dict) and "tool" in data and "params" in data:
            return _validate_tool_name(data)
    except Exception:
        pass

    # 5. Regex extraction fallback for tool + params if JSON decoding failed
    tool_match = re.search(r'"tool"\s*:\s*"([^"]+)"', candidate)
    if tool_match:
        tool_name = tool_match.group(1)
        if tool_name in PLACEHOLDER_TOOL_NAMES:
            return None
        params: dict = {}

        # Extract path (many alias variants)
        path_aliases = [
            "filePath", "filepath", "file_path", "targetFile", "target_file",
            "filename", "file_name", "targetPath", "target_path",
            "dest", "destination", "src", "source",
        ]
        path_val = _extract_param_fallback(candidate, "path", path_aliases)
        if path_val is not None:
            params["path"] = path_val

        # Extract content
        content_val = _extract_param_fallback(candidate, "content")
        if content_val is not None:
            params["content"] = content_val

        # Extract old_content / search / find
        old_aliases = ["oldContent", "search", "find", "old_string", "original", "oldtext", "targettext"]
        old_val = _extract_param_fallback(candidate, "old_content", old_aliases)
        if old_val is not None:
            params["old_content"] = old_val

        # Extract new_content / replace / replacement
        new_aliases = ["newContent", "replace", "new_string", "replacement", "newtext", "replacementtext"]
        new_val = _extract_param_fallback(candidate, "new_content", new_aliases)
        if new_val is not None:
            params["new_content"] = new_val

        # Extract command
        cmd_val = _extract_param_fallback(candidate, "command", ["cmd", "commandString", "script", "exec", "run"])
        if cmd_val is not None:
            params["command"] = cmd_val

        # Extract pattern (for glob/grep)
        pattern_val = _extract_param_fallback(candidate, "pattern", ["query", "glob", "searchPattern", "filter", "regex"])
        if pattern_val is not None:
            params["pattern"] = pattern_val

        # Extract URL (for webfetch)
        url_val = _extract_param_fallback(candidate, "url")
        if url_val is not None:
            params["url"] = url_val

        # Extract include (for grep file filter)
        include_val = _extract_param_fallback(candidate, "include")
        if include_val is not None:
            params["include"] = include_val

        # Extract timeout (for bash/webfetch)
        timeout_match = re.search(r'"timeout"\s*:\s*(\d+)', candidate)
        if timeout_match:
            params["timeout"] = int(timeout_match.group(1))

        if tool_name:
            return {"tool": tool_name, "params": params}

    return None


def parse_tool_calls(text: str) -> list[dict]:
    """Extract and parse all tool calls from a text response."""
    from tools.param_normalizer import normalize_file_params

    calls: list[dict] = []
    seen: set[str] = set()
    matched_spans: list[tuple[int, int]] = []

    def _add_call(parsed: dict) -> bool:
        """Add a parsed tool call if valid and not duplicate. Returns True if added."""
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
            if any(s <= start and end <= e for s, e in matched_spans):
                continue

            candidate = match.group(1) if len(match.groups()) > 0 else match.group(0)
            candidate = candidate.strip()

            # Try parsing as JSON array first (for models that emit [{"tool":...},...])
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

            # Single tool call object
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

    return calls



def clean_tool_text(text: str) -> str:
    """Clean out tool call blocks, inline tool JSON, and hallucinated output text from assistant messages."""
    # Fenced single tool blocks
    cleaned = re.sub(
        r"```(?:tool|json)?\s*\n?\{[\s\S]*?\"tool\"\s*:\s*\"[^\"]+\"[\s\S]*?\}\s*\n?```",
        "", text, flags=re.IGNORECASE,
    )
    # Inline single tool JSON
    cleaned = re.sub(
        r"\{[\s\S]*?\"tool\"\s*:\s*\"[^\"]+\"[\s\S]*?\"params\"\s*:\s*\{[\s\S]*?\}\s*\}",
        "", cleaned,
    )
    # Fenced JSON arrays of tool calls
    cleaned = re.sub(
        r"```(?:tool|json)?\s*\n?\[[\s\S]*?\"tool\"\s*:\s*\"[^\"]+\"[\s\S]*?\]\s*\n?```",
        "", cleaned, flags=re.IGNORECASE,
    )
    # Inline JSON arrays of tool calls
    cleaned = re.sub(
        r"\[[\s\S]*?\{[\s\S]*?\"tool\"\s*:\s*\"[^\"]+\"[\s\S]*?\}[\s\S]*?\]",
        "", cleaned,
    )
    # Remove hallucinated mock output blocks (only when they look like structured output, not natural prose)
    cleaned = re.sub(r"^Command:\s+.*$\n^Output:.*$", "", cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r"^Successfully (?:created|wrote|deleted|edited) (?:new )?file:\s*[^\n]+$", "", cleaned, flags=re.MULTILINE | re.IGNORECASE)
    # Remove placeholder patterns
    cleaned = re.sub(r"\[(?:PASTE|INSERT|TODO|HTML|UPDATED|ACTUAL|CURRENT|DESIRED)[^\]]{0,50}\]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bYOUR_[\w_]+_HERE\b", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


class UnifiedResponseFormatter:
    """Unified response formatter — native FC only, no text-based parsing."""

    @staticmethod
    def process_response(raw_content: str, raw_tool_calls: list[dict] | None = None) -> tuple[str, list[dict]]:
        tool_calls = []

        # Only remap native tool_calls from OpenAI format to our internal format
        if raw_tool_calls:
            for tc in raw_tool_calls:
                remapped = UnifiedResponseFormatter._remap_native_tool_call(tc)
                if remapped:
                    tool_calls.append(remapped)

        clean_text = clean_tool_text(raw_content)
        return clean_text, tool_calls

    @staticmethod
    def _remap_native_tool_call(tc: dict) -> dict | None:
        """Remap a native OpenAI tool_call to our internal {tool, params} format."""
        # OpenAI format: {"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}
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

        # Already in our format
        if "tool" in tc:
            params = tc.get("params", {})
            if not isinstance(params, dict):
                params = {}
            return {"tool": tc["tool"], "params": params}

        return None

