from __future__ import annotations

import json
import re
import logging
from typing import AsyncIterator

from .adapters import Chunk, ModelResponse

logger = logging.getLogger(__name__)

TOOL_PATTERNS = [
    re.compile(r"```(?:tool|json)?\s*\n?(\{[\s\S]*?\"tool\"\s*:\s*\"[^\"]+\"[\s\S]*?\})\s*\n?```", re.IGNORECASE),
    re.compile(r"(\{[\s\S]*?\"tool\"\s*:\s*\"[^\"]+\"[\s\S]*?\"params\"\s*:\s*\{[\s\S]*?\}\s*\})"),
]

UNCLOSED_PATTERN = re.compile(r"```(?:tool|json)?\s*\n?(\{[\s\S]*?\"tool\"\s*:\s*\"[^\"]+\"[\s\S]*)$", re.IGNORECASE)


def _repair_and_parse_json(candidate: str) -> dict | None:
    """Repair dirty/unclosed JSON emitted by LLMs (e.g. unescaped newlines/quotes) and parse to dict."""
    cleaned_cand = re.sub(r"^```(?:tool|json)?\s*", "", candidate.strip(), flags=re.IGNORECASE)
    cleaned_cand = re.sub(r"\s*```$", "", cleaned_cand).strip()

    # 1. Standard json.loads (non-strict allows control chars)
    try:
        data = json.loads(cleaned_cand, strict=False)
        if isinstance(data, dict) and "tool" in data and "params" in data:
            return data
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
            return data
    except Exception:
        pass

    # 3. Fix invalid backslash escapes (Windows paths like \v, \c)
    sanitized = re.sub(r'\\(?![\\"/bfnrtu])', '/', cleaned_cand)
    try:
        data = json.loads(sanitized, strict=False)
        if isinstance(data, dict) and "tool" in data and "params" in data:
            return data
    except Exception:
        pass

    # 4. Handle trailing commas before closing braces
    fixed_commas = re.sub(r",\s*([\}\]])", r"\1", sanitized)
    try:
        data = json.loads(fixed_commas, strict=False)
        if isinstance(data, dict) and "tool" in data and "params" in data:
            return data
    except Exception:
        pass

    # 5. Regex extraction fallback for tool + params if JSON decoding failed due to multiline text
    tool_match = re.search(r'"tool"\s*:\s*"([^"]+)"', candidate)
    if tool_match:
        tool_name = tool_match.group(1)
        params: dict = {}

        # Extract filepath if present
        fp_match = re.search(r'"(?:filepath|file_path|path)"\s*:\s*"([^"]+)"', candidate)
        if fp_match:
            params["filepath"] = fp_match.group(1)

        # Extract content if present
        content_match = re.search(r'"content"\s*:\s*"(.*)"\s*\}\s*\}?\s*$', candidate, re.DOTALL)
        if not content_match:
            content_match = re.search(r'"content"\s*:\s*"(.*?)"\s*,\s*"', candidate, re.DOTALL)
        if content_match:
            raw_content = content_match.group(1)
            params["content"] = raw_content.replace(r'\"', '"').replace(r'\\n', '\n')

        # Extract command if present
        cmd_match = re.search(r'"command"\s*:\s*"([^"]+)"', candidate)
        if cmd_match:
            params["command"] = cmd_match.group(1)

        if tool_name and params:
            return {"tool": tool_name, "params": params}

    return None


def parse_tool_calls(text: str) -> list[dict]:
    """Extract and parse all tool calls from a text response."""
    calls: list[dict] = []
    seen: set[str] = set()
    for pattern in TOOL_PATTERNS:
        for match in pattern.finditer(text):
            candidate = match.group(1) if len(match.groups()) > 0 else match.group(0)
            candidate = candidate.strip()
            parsed = _repair_and_parse_json(candidate)
            if parsed:
                sig = json.dumps(parsed, sort_keys=True)
                if sig not in seen:
                    calls.append(parsed)
                    seen.add(sig)

    if not calls:
        match = UNCLOSED_PATTERN.search(text)
        if match:
            candidate = match.group(1).strip()
            parsed = _repair_and_parse_json(candidate)
            if parsed:
                calls.append(parsed)

    return calls


def clean_tool_text(text: str) -> str:
    """Clean out tool call blocks, inline tool JSON, and hallucinated output text from assistant messages."""
    cleaned = re.sub(
        r"```(?:tool|json)?\s*\n?\{[\s\S]*?\"tool\"\s*:\s*\"[^\"]+\"[\s\S]*?\}\s*\n?```",
        "", text, flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\{[\s\S]*?\"tool\"\s*:\s*\"[^\"]+\"[\s\S]*?\"params\"\s*:\s*\{[\s\S]*?\}\s*\}",
        "", cleaned,
    )
    # Remove hallucinated mock output blocks like Command: ... Output: ... or Successfully created new file...
    cleaned = re.sub(r"Command:\s*cd\s+.*?\nOutput:[\s\S]*?(?=\n\n|\Z)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Successfully created new file:\s*[^\n]+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


class UnifiedResponseFormatter:
    """Unified response formatter standardizing output across all model provider adapters."""

    @staticmethod
    def process_response(raw_content: str, raw_tool_calls: list[dict] | None = None) -> tuple[str, list[dict]]:
        tool_calls = list(raw_tool_calls) if raw_tool_calls else []

        # Parse inline tool calls from raw content if present
        text_tool_calls = parse_tool_calls(raw_content)
        for tc in text_tool_calls:
            if tc not in tool_calls:
                tool_calls.append(tc)

        clean_text = clean_tool_text(raw_content)
        return clean_text, tool_calls


async def accumulate_stream(stream: AsyncIterator[Chunk]) -> ModelResponse:
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    native_tool_calls: list[dict] = []
    finish_reason: str | None = None

    async for chunk in stream:
        if chunk.content:
            content_parts.append(chunk.content)
        if chunk.reasoning:
            reasoning_parts.append(chunk.reasoning)
        if chunk.tool_calls:
            native_tool_calls.extend(chunk.tool_calls)
        if chunk.finish_reason:
            finish_reason = chunk.finish_reason

    raw_text = "".join(content_parts)
    clean_text, tool_calls = UnifiedResponseFormatter.process_response(raw_text, native_tool_calls)
    reasoning_text = "".join(reasoning_parts)

    return ModelResponse(
        content=clean_text,
        reasoning=reasoning_text,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
    )

