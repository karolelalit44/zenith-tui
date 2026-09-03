from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    COST_CLASS_MEDIUM,
    DEFAULT_USER_AGENT,
    DEFAULT_WEB_TIMEOUT,
    DEFAULT_WEBFETCH_MAX_BYTES,
    LATENCY_CLASS_HIGH,
    PERMISSION_NETWORK,
    RISK_LOW,
    TOOL_DOMAIN_WEB,
    URL_SCHEME_RE,
    WEBFETCH_MAX_BYTES_ENV,
    WEBFETCH_TIMEOUT_ENV,
)
from server.config.env import optional_int

from ..base import BaseTool, ToolResult
from ._html_text import html_to_markdown

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CHARS = optional_int(WEBFETCH_MAX_BYTES_ENV, DEFAULT_WEBFETCH_MAX_BYTES)


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
) -> FetchResult:
    """Fetch *url* and convert it to Markdown — pure fetch + convert, no LLM extraction.

    Matches opencode's ``tool/webfetch.ts``: a plain GET plus HTML→Markdown
    conversion capped at ``max_chars``. Raises on transport/HTTP errors; parse
    failures degrade gracefully to the raw (truncated) text.
    """
    import httpx

    if timeout is None:
        timeout = optional_int(WEBFETCH_TIMEOUT_ENV, DEFAULT_WEB_TIMEOUT)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": user_agent},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    raw = response.text
    if "html" in content_type:
        markdown = html_to_markdown(raw, max_chars=max_chars)
    else:
        markdown = raw[:max_chars]
    truncated = len(markdown) >= max_chars and len(raw) > max_chars
    if truncated:
        markdown += f"\n\n[...truncated at {max_chars} chars; fetched page was {len(raw)} chars]"
    return FetchResult(
        url=url,
        content_type=content_type,
        chars=len(raw),
        markdown=markdown,
        truncated=truncated,
    )


class WebfetchTool(BaseTool):
    name = "webfetch"
    description = (
        "Fetch a URL and read its content. Returns the page converted to clean "
        "Markdown (never raw HTML). "
        "Use websearch to find sources, then webfetch to read one specific page."
    )
    capability_id = "web_fetch"
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_NETWORK
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
                    "description": "URL to fetch (http/https only)",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters of content to return",
                    "default": _DEFAULT_MAX_CHARS,
                    "minimum": 1000,
                    "maximum": 200000,
                },
            },
            "required": ["url"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        url = params.get("url", "").strip()
        if not url:
            return ToolResult(success=False, error="No URL provided")
        if not URL_SCHEME_RE.match(url):
            return ToolResult(success=False, error=f"Only http/https URLs are supported: {url}")
        try:
            max_chars = int(params.get("max_chars", _DEFAULT_MAX_CHARS))
        except (TypeError, ValueError):
            max_chars = _DEFAULT_MAX_CHARS
        max_chars = max(1000, min(max_chars, 200000))
        try:
            fetched = await fetch_page(url, max_chars=max_chars)
            markdown = fetched.markdown
            content_type = fetched.content_type
            if not markdown.strip():
                return ToolResult(
                    success=True,
                    output="Page fetched but no readable text content was found.",
                    metadata={"url": url, "content_type": content_type, "chars": fetched.chars},
                )
            metadata = {"url": url, "content_type": content_type, "chars": fetched.chars}
            return ToolResult(success=True, output=markdown, metadata=metadata)
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to fetch {url}: {e}")
