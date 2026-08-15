from __future__ import annotations

import os
import re
import urllib.parse
from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    COST_CLASS_MEDIUM,
    DEFAULT_USER_AGENT,
    DEFAULT_WEB_TIMEOUT,
    LATENCY_CLASS_HIGH,
    PERMISSION_NETWORK,
    RISK_LOW,
    TOOL_DOMAIN_WEB_MCP,
    WEBSEARCH_TIMEOUT_ENV,
)
from server.config.env import optional_int

from ..base import BaseTool, ToolResult

_DEFAULT_MAX_RESULTS = 8


class WebsearchTool(BaseTool):
    name = "websearch"
    description = (
        "Search the web for a query and return result titles, URLs, and snippets. "
        "Use websearch to find credible sources, then webfetch to read a specific page. "
        "Returns a compact list of results, never raw HTML."
    )
    capability_id = "web_search"
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_NETWORK
    domains = (TOOL_DOMAIN_WEB_MCP,)
    search_terms = (
        "web",
        "search",
        "query",
        "google",
        "bing",
        "research",
        "find",
        "sources",
    )
    risk_level = RISK_LOW
    cost_class = COST_CLASS_MEDIUM
    latency_class = LATENCY_CLASS_HIGH

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (1-10)",
                    "default": _DEFAULT_MAX_RESULTS,
                    "minimum": 1,
                    "maximum": 10,
                },
                "allowed_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Restrict results to these domains (e.g. ['github.com'])",
                },
            },
            "required": ["query"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        query = (params.get("query") or "").strip()
        if not query:
            return ToolResult(success=False, error="No search query provided")
        try:
            max_results = min(int(params.get("max_results", _DEFAULT_MAX_RESULTS)), 10)
        except (TypeError, ValueError):
            max_results = _DEFAULT_MAX_RESULTS
        allowed_domains = params.get("allowed_domains") or []

        api = os.environ.get("ZENITH_SEARCH_API", "").strip().lower()
        key = os.environ.get("ZENITH_SEARCH_API_KEY", "").strip()
        try:
            if api and key:
                results = await self._search_api(api, key, query, max_results)
                source = f"{api} search"
            else:
                results = await self._search_duckduckgo(query, max_results)
                source = "DuckDuckGo"
        except Exception as e:
            return ToolResult(success=False, error=f"Search failed: {e}")

        if allowed_domains:
            domains = {d.lower().lstrip(".") for d in allowed_domains}
            results = [
                r for r in results if any(dom in (r.get("url") or "").lower() for dom in domains)
            ][:max_results]

        if not results:
            return ToolResult(
                success=True,
                output="No results found.",
                metadata={"query": query, "source": source, "count": 0},
            )
        lines = [f"Search results for '{query}' ({source}):"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.get('title') or '(no title)'}")
            lines.append(f"   {r.get('url') or ''}")
            snippet = (r.get("snippet") or "").strip()
            if snippet:
                lines.append(f"   {snippet}")
        return ToolResult(
            success=True,
            output="\n".join(lines),
            metadata={"query": query, "source": source, "count": len(results)},
        )

    # â”€â”€ backends â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _search_api(
        self, api: str, key: str, query: str, max_results: int
    ) -> list[dict[str, str]]:
        import httpx

        headers = {"User-Agent": DEFAULT_USER_AGENT}
        if api == "tavily":
            url = "https://api.tavily.com/search"
            body = {"api_key": key, "query": query, "max_results": max_results}
            async with httpx.AsyncClient(timeout=optional_int(WEBSEARCH_TIMEOUT_ENV, DEFAULT_WEB_TIMEOUT)) as client:
                data = (await client.post(url, json=body, headers=headers)).json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                }
                for r in data.get("results", [])[:max_results]
            ]
        if api == "brave":
            url = "https://api.search.brave.com/res/v1/web/search"
            headers["X-Subscription-Token"] = key
            async with httpx.AsyncClient(timeout=optional_int(WEBSEARCH_TIMEOUT_ENV, DEFAULT_WEB_TIMEOUT)) as client:
                data = (await client.get(url, params={"q": query}, headers=headers)).json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("description", ""),
                }
                for r in data.get("web", {}).get("results", [])[:max_results]
            ]
        if api == "serper":
            url = "https://google.serper.dev/search"
            headers["X-API-KEY"] = key
            async with httpx.AsyncClient(timeout=optional_int(WEBSEARCH_TIMEOUT_ENV, DEFAULT_WEB_TIMEOUT)) as client:
                data = (await client.post(url, json={"q": query}, headers=headers)).json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("link", ""),
                    "snippet": r.get("snippet", ""),
                }
                for r in data.get("organic", [])[:max_results]
            ]
        if api == "bing":
            url = "https://api.bing.microsoft.com/v7.0/search"
            headers["Ocp-Apim-Subscription-Key"] = key
            async with httpx.AsyncClient(timeout=optional_int(WEBSEARCH_TIMEOUT_ENV, DEFAULT_WEB_TIMEOUT)) as client:
                data = (await client.get(url, params={"q": query}, headers=headers)).json()
            return [
                {
                    "title": r.get("name", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", ""),
                }
                for r in data.get("webPages", {}).get("value", [])[:max_results]
            ]
        raise ValueError(f"Unknown search API '{api}' (expected tavily|brave|serper|bing)")

    async def _search_duckduckgo(self, query: str, max_results: int) -> list[dict[str, str]]:
        """No-key fallback: scrape the DuckDuckGo HTML endpoint."""
        import httpx

        url = "https://html.duckduckgo.com/html/"
        headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "text/html"}
        async with httpx.AsyncClient(timeout=optional_int(WEBSEARCH_TIMEOUT_ENV, DEFAULT_WEB_TIMEOUT), follow_redirects=True) as client:
            response = await client.get(url, params={"q": query}, headers=headers)
            response.raise_for_status()
        return _parse_ddg_results(response.text)[:max_results]


def _parse_ddg_results(page: str) -> list[dict[str, str]]:
    """Parse DuckDuckGo HTML results (title/url/snippet), unwrapping redirects."""

    def _clean(s: str) -> str:
        import html as _html

        if not s:
            return ""
        s = re.sub(r"<[^>]+>", "", s)  # strip tags like <b>/<em> in snippets
        return re.sub(r"\s+", " ", _html.unescape(s).strip())

    results: list[dict[str, str]] = []
    for m in re.finditer(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page, re.DOTALL):
        href = m.group(1)
        if href.startswith("//duckduckgo.com/l/?uddg="):
            encoded = href.split("uddg=", 1)[1].split("&", 1)[0]
            href = urllib.parse.unquote(encoded)
        elif not href.startswith("http"):
            continue
        results.append({"title": _clean(m.group(2)), "url": href, "snippet": ""})
    snips = list(re.finditer(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', page, re.DOTALL))
    for i, sm in enumerate(snips):
        if i < len(results):
            results[i]["snippet"] = _clean(sm.group(1))
    return results
