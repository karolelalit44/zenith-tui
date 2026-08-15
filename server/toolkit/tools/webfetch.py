from __future__ import annotations

import logging
import os
import re
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
    TOOL_DOMAIN_WEB_MCP,
    WEBFETCH_MAX_BYTES_ENV,
    WEBFETCH_TIMEOUT_ENV,
)
from server.config.env import optional_int

from ..base import BaseTool, ToolResult
from ._html_text import html_to_markdown

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CHARS = optional_int(WEBFETCH_MAX_BYTES_ENV, DEFAULT_WEBFETCH_MAX_BYTES)
# Content fed to the extractor model is capped tighter so the extraction call
# stays cheap and low-latency (Claude Code's WebFetch is "lossy by design").
_EXTRACT_MAX_CHARS = 25000


class WebfetchTool(BaseTool):
    name = "webfetch"
    description = (
        "Fetch a URL and read its content. By default returns the page converted to clean "
        "Markdown (never raw HTML). For long pages, pass an 'extract' question to get just "
        "the answer to that question instead of the full page. "
        "Use websearch to find sources, then webfetch to read one specific page."
    )
    capability_id = "web_fetch"
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_NETWORK
    domains = (TOOL_DOMAIN_WEB_MCP,)
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
        self._extract_model = os.environ.get("ZENITH_EXTRACT_MODEL", "").strip() or None

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch (http/https only)",
                },
                "extract": {
                    "type": "string",
                    "description": (
                        "Optional. A specific question to answer from the page. When provided, "
                        "a fast model extracts just the answer from the page content (lossy but "
                        "context-efficient). When omitted, returns the full page as clean Markdown."
                    ),
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
        if not re.match(r"^https?://", url, re.IGNORECASE):
            return ToolResult(success=False, error=f"Only http/https URLs are supported: {url}")
        try:
            max_chars = int(params.get("max_chars", _DEFAULT_MAX_CHARS))
        except (TypeError, ValueError):
            max_chars = _DEFAULT_MAX_CHARS
        max_chars = max(1000, min(max_chars, 200000))
        try:
            import httpx

            async with httpx.AsyncClient(
                timeout=optional_int(WEBFETCH_TIMEOUT_ENV, DEFAULT_WEB_TIMEOUT),
                follow_redirects=True,
                headers={"User-Agent": DEFAULT_USER_AGENT},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            raw = response.text
            if "html" in content_type:
                markdown = html_to_markdown(raw, max_chars=max_chars)
            else:
                # Plain text / JSON / etc. — cap it and report.
                markdown = raw[:max_chars]
            truncated = len(markdown) >= max_chars and len(raw) > max_chars
            if truncated:
                markdown += (
                    f"\n\n[...truncated at {max_chars} chars; fetched page was {len(raw)} chars]"
                )
            if not markdown.strip():
                return ToolResult(
                    success=True,
                    output="Page fetched but no readable text content was found.",
                    metadata={"url": url, "content_type": content_type, "chars": len(raw)},
                )
            extract = (params.get("extract") or "").strip()
            metadata = {"url": url, "content_type": content_type, "chars": len(raw)}
            if extract and self._provider is not None:
                answer = await self._extract_answer(markdown, extract)
                if answer is not None:
                    metadata["extracted"] = True
                    metadata["source_chars"] = len(markdown)
                    return ToolResult(success=True, output=answer, metadata=metadata)
                # Extraction failed; fall back to the full content with a note.
                markdown = (
                    f"[Webfetch extraction was unavailable; page content follows]\n\n{markdown}"
                )
            elif extract:
                markdown = (
                    f"[Webfetch extraction requested but no model is available; "
                    f"page content follows]\n\n{markdown}"
                )
            return ToolResult(success=True, output=markdown, metadata=metadata)
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to fetch {url}: {e}")

    async def _extract_answer(self, content: str, question: str) -> str | None:
        """Have a fast model answer `question` against `content` (lossy by design)."""
        if self._provider is None:
            return None
        try:
            excerpt = content[:_EXTRACT_MAX_CHARS]
            prompt = (
                "Read the page content below and answer the question. "
                "Answer concisely, based ONLY on the content. If the page does not "
                "contain the information, say exactly: 'The page does not contain "
                "this information.' Do not mention the page content format.\n\n"
                f"PAGE CONTENT:\n{excerpt}\n\n"
                f"QUESTION: {question}\nANSWER:"
            )
            answer = await self._provider.complete(
                [{"role": "user", "content": prompt}], model=self._extract_model
            )
            answer = (answer or "").strip()
            return answer or None
        except Exception:
            logger.exception("webfetch extraction failed")
            return None
