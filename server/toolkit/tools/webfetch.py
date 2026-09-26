from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    COST_CLASS_MEDIUM,
    DEFAULT_USER_AGENT,
    LATENCY_CLASS_HIGH,
    RISK_LOW,
    TOOL_DOMAIN_WEB,
    is_http_url,
)
from server.config.environment import ZENITH_WEBFETCH_MAX_BYTES, ZENITH_WEBFETCH_TIMEOUT

from ..base import BaseTool, ToolResult
from ._html_text import html_to_markdown, html_to_plain_text
from ._transport import (
    PayloadTooLargeError,
    RedirectSecurityError,
    SSRFSecurityError,
    TransportSecurityError,
    secure_fetch,
)
from ._web_cache import CachedDocument, get_web_cache

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CHARS = ZENITH_WEBFETCH_MAX_BYTES


@dataclass
class FetchResult:
    """Result of a pure fetch + convert-to-Markdown operation (opencode-style).

    Never contains raw HTML; the page is always converted to clean Markdown and
    truncated to ``max_chars``.
    """

    url: str
    content_type: str
    chars: int
    markdown: str
    truncated: bool


async def fetch_page(
    url: str,
    *,
    max_chars: int = _DEFAULT_MAX_CHARS,
    timeout: int | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    secure: bool = False,
) -> FetchResult:
    """Fetch *url* and convert it to Markdown — pure fetch + convert, no LLM extraction.

    Matches opencode's ``tool/webfetch.ts``: a plain GET plus HTML→Markdown
    conversion capped at ``max_chars``. Raises on transport/HTTP errors; parse
    failures degrade gracefully to the raw (truncated) text.
    """
    if secure:
        resp = await secure_fetch(url, timeout=timeout, user_agent=user_agent)
        content_type = resp.content_type
        raw = resp.text
        final_url = resp.url
    else:
        import httpx

        if timeout is None:
            timeout = ZENITH_WEBFETCH_TIMEOUT
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        raw = response.text
        final_url = url

    if "html" in content_type:
        markdown = html_to_markdown(raw, max_chars=max_chars, base_url=final_url)
    else:
        markdown = raw[:max_chars]
    truncated = len(markdown) >= max_chars and len(raw) > max_chars
    if truncated:
        markdown += f"\n\n[...truncated at {max_chars} chars; fetched page was {len(raw)} chars]"
    return FetchResult(
        url=final_url,
        content_type=content_type,
        chars=len(raw),
        markdown=markdown,
        truncated=truncated,
    )


class WebfetchTool(BaseTool):
    name = "webfetch"
    description = (
        "Fetch a web URL and inspect its content in clean Markdown or text. "
        "Supports targeted line slicing (start_line, end_line) and in-page pattern search (pattern). "
        "Use websearch to discover sources first; use webfetch to read specific pages. "
        "Never use for local files (use file_read)."
    )
    capability_id = "web_fetch"
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    domains = (TOOL_DOMAIN_WEB,)
    search_terms = (
        "web",
        "fetch",
        "url",
        "http",
        "download",
        "page",
        "link",
        "read",
        "content",
        "search_page",
        "find_in_page",
    )
    risk_level = RISK_LOW
    cost_class = COST_CLASS_MEDIUM
    latency_class = LATENCY_CLASS_HIGH

    def __init__(self, provider: Any | None = None) -> None:
        self._provider = provider

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": (
                        "URL to fetch (http/https only) or reference token (e.g. 'ref_doc_1')"
                    ),
                },
                "start_line": {
                    "type": "integer",
                    "description": "1-indexed starting line number for targeted window inspection",
                    "minimum": 1,
                },
                "end_line": {
                    "type": "integer",
                    "description": "1-indexed ending line number for targeted window inspection",
                    "minimum": 1,
                },
                "pattern": {
                    "type": "string",
                    "description": "Text pattern or regex to search inside the document (find_in_page mode)",
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Number of context lines before and after matches when searching with pattern",
                    "default": 3,
                    "minimum": 0,
                    "maximum": 10,
                },
                "max_matches": {
                    "type": "integer",
                    "description": "Maximum number of search pattern matches to return",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters of content to return in full document mode",
                    "default": _DEFAULT_MAX_CHARS,
                    "minimum": 1000,
                    "maximum": 100000,
                },
                "as_text": {
                    "type": "boolean",
                    "description": "If true, returns stripped plain text instead of formatted Markdown",
                    "default": False,
                },
            },
            "required": ["url"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        raw_target = params.get("url", "").strip()
        if not raw_target:
            return ToolResult(success=False, error="No URL or reference token provided")

        cache = get_web_cache()
        resolved_url = cache.resolve_url(raw_target)

        if not is_http_url(resolved_url):
            return ToolResult(
                success=False,
                error=f"Only http/https URLs are supported: {resolved_url}",
            )

        # 1. Retrieve from session cache or perform secure fetch
        doc: CachedDocument | None = cache.get(resolved_url)
        as_text = bool(params.get("as_text", False))

        if doc is None:
            try:
                resp = await secure_fetch(resolved_url)
            except SSRFSecurityError as e:
                return ToolResult(success=False, error=f"Security error: {e}")
            except PayloadTooLargeError as e:
                return ToolResult(success=False, error=f"Payload too large: {e}")
            except RedirectSecurityError as e:
                return ToolResult(success=False, error=f"Redirect security error: {e}")
            except TransportSecurityError as e:
                return ToolResult(success=False, error=f"Transport security error: {e}")
            except Exception as e:
                return ToolResult(success=False, error=f"Failed to fetch {resolved_url}: {e}")

            # Multimodal image handling
            if resp.is_image or resp.content_type.startswith("image/"):
                b64 = base64.b64encode(resp.body_bytes).decode("ascii")
                data_uri = f"data:{resp.content_type};base64,{b64}"
                doc = cache.put(
                    url=resp.url,
                    content_type=resp.content_type,
                    markdown=f"![Image]({resp.url})",
                    chars=len(resp.body_bytes),
                    is_image=True,
                    base64_data=data_uri,
                )
                return ToolResult(
                    success=True,
                    output=(
                        f"Image fetched successfully ({resp.content_type}, {len(resp.body_bytes)} bytes).\n"
                        f"Data URI: {data_uri[:100]}... [total base64 length: {len(b64)}]"
                    ),
                    metadata={
                        "url": resp.url,
                        "content_type": resp.content_type,
                        "is_image": True,
                        "base64": b64,
                        "bytes": len(resp.body_bytes),
                        "ref": doc.ref_id,
                    },
                )

            # Block binary downloads
            if any(
                b in resp.content_type
                for b in (
                    "application/pdf",
                    "application/zip",
                    "application/gzip",
                    "application/octet-stream",
                    "application/x-tar",
                )
            ):
                return ToolResult(
                    success=False,
                    error=(
                        f"Unsupported binary document format '{resp.content_type}'. "
                        "Zenith webfetch extracts HTML, Markdown, and plain text documents."
                    ),
                )

            # Convert to Markdown or plain text
            if "html" in resp.content_type or resp.content_type in ("text/html", "application/xhtml+xml"):
                markdown = html_to_plain_text(resp.text) if as_text else html_to_markdown(resp.text, base_url=resp.url)
            else:
                markdown = resp.text

            doc = cache.put(
                url=resp.url,
                content_type=resp.content_type,
                markdown=markdown,
                chars=len(resp.text),
            )

        # 2. Mode A: In-page pattern search (find_in_page)
        pattern = params.get("pattern", "").strip() if params.get("pattern") else ""
        if pattern:
            try:
                context_lines = max(0, min(10, int(params.get("context_lines", 3))))
            except (TypeError, ValueError):
                context_lines = 3
            try:
                max_matches = max(1, min(20, int(params.get("max_matches", 5))))
            except (TypeError, ValueError):
                max_matches = 5

            try:
                regex = re.compile(pattern, re.IGNORECASE)
            except re.error:
                regex = re.compile(re.escape(pattern), re.IGNORECASE)

            matching_indices = [
                idx for idx, line in enumerate(doc.lines) if regex.search(line)
            ]

            if not matching_indices:
                return ToolResult(
                    success=True,
                    output=(
                        f"No matches found for pattern '{pattern}' in {doc.url} "
                        f"({doc.total_lines} total lines).\n"
                        "Suggestions: check spelling, search for shorter keywords, "
                        "or read sections using start_line and end_line."
                    ),
                    metadata={
                        "url": doc.url,
                        "matches": 0,
                        "total_lines": doc.total_lines,
                        "ref": doc.ref_id,
                    },
                )

            snippets: list[str] = []
            for m_idx in matching_indices[:max_matches]:
                s_start = max(0, m_idx - context_lines)
                s_end = min(doc.total_lines, m_idx + context_lines + 1)
                block: list[str] = []
                for line_num in range(s_start + 1, s_end + 1):
                    marker = ">>> " if line_num == m_idx + 1 else "    "
                    block.append(f"{marker}L{line_num}: {doc.lines[line_num - 1]}")
                snippets.append("\n".join(block))

            header = (
                f'# Search Results for "{pattern}" in {doc.url} (Reference: {doc.ref_id})\n'
                f"Found {len(matching_indices)} match(es) across {doc.total_lines} lines "
                f"(showing first {min(len(matching_indices), max_matches)}):\n\n"
            )
            output = header + "\n\n---\n\n".join(snippets)
            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "url": doc.url,
                    "pattern": pattern,
                    "matches": len(matching_indices),
                    "shown": min(len(matching_indices), max_matches),
                    "total_lines": doc.total_lines,
                    "ref": doc.ref_id,
                },
            )

        # 3. Mode B: Line range offset reading
        raw_start = params.get("start_line")
        raw_end = params.get("end_line")
        if raw_start is not None or raw_end is not None:
            try:
                start_line = int(raw_start) if raw_start is not None else 1
                end_line = int(raw_end) if raw_end is not None else doc.total_lines
            except (TypeError, ValueError):
                return ToolResult(
                    success=False,
                    error="start_line and end_line must be positive integers",
                )

            if start_line < 1:
                start_line = 1
            if end_line < start_line:
                return ToolResult(
                    success=False,
                    error=(
                        f"Invalid line range: start_line ({start_line}) cannot be "
                        f"greater than end_line ({end_line})"
                    ),
                )

            clamped_end = min(end_line, doc.total_lines)
            sliced = doc.lines[start_line - 1 : clamped_end]
            formatted_lines = [f"L{start_line + i}: {line}" for i, line in enumerate(sliced)]
            body = "\n".join(formatted_lines)
            header = (
                f"# Content of {doc.url} (Reference: {doc.ref_id})\n"
                f"Showing lines {start_line}-{clamped_end} of {doc.total_lines} total lines "
                f"({sum(len(l) for l in sliced)} characters):\n\n"
            )
            return ToolResult(
                success=True,
                output=header + body,
                metadata={
                    "url": doc.url,
                    "start_line": start_line,
                    "end_line": clamped_end,
                    "total_lines": doc.total_lines,
                    "ref": doc.ref_id,
                },
            )

        # 4. Mode C: Full document reading with visible truncation contract
        try:
            max_chars = int(params.get("max_chars", _DEFAULT_MAX_CHARS))
        except (TypeError, ValueError):
            max_chars = _DEFAULT_MAX_CHARS
        max_chars = max(1000, min(max_chars, 100000))

        content = doc.markdown
        if not content.strip():
            return ToolResult(
                success=True,
                output=(
                    f"Page {doc.url} (Reference: {doc.ref_id}) was fetched successfully, "
                    "but no readable text content was found."
                ),
                metadata={
                    "url": doc.url,
                    "content_type": doc.content_type,
                    "chars": doc.chars,
                    "ref": doc.ref_id,
                },
            )

        is_truncated = len(content) > max_chars
        if is_truncated:
            cutoff = content.rfind("\n", 0, max_chars)
            if cutoff < max_chars // 2:
                cutoff = max_chars
            sliced_content = content[:cutoff]
            notice = (
                f"\n\n[TRUNCATION NOTICE: Content truncated at {len(sliced_content)} characters. "
                f"Total document size was {doc.chars} characters across {doc.total_lines} lines. "
                "To inspect subsequent sections, re-invoke webfetch with start_line and end_line parameters, "
                "or use pattern to search for specific terms.]"
            )
            output = sliced_content + notice
        else:
            output = content

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "url": doc.url,
                "content_type": doc.content_type,
                "chars": doc.chars,
                "lines": doc.total_lines,
                "truncated": is_truncated,
                "ref": doc.ref_id,
            },
        )
