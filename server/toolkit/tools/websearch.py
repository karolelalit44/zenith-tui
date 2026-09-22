from __future__ import annotations

import asyncio
import logging
import os
import re
import urllib.parse
from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    COST_CLASS_MEDIUM,
    DEFAULT_USER_AGENT,
    DEFAULT_WEBSEARCH_MAX_RESULTS,
    LATENCY_CLASS_HIGH,
    PERMISSION_NETWORK,
    RISK_LOW,
    TOOL_DOMAIN_WEB,
)
from server.config.environment import ZENITH_WEBSEARCH_TIMEOUT

from ..base import BaseTool, ToolResult
from ._web_cache import get_web_cache

logger = logging.getLogger(__name__)

_DEFAULT_MAX_RESULTS = DEFAULT_WEBSEARCH_MAX_RESULTS
_MAX_QUERY_BATCH_SIZE = 4


class WebsearchTool(BaseTool):
    name = "websearch"
    description = (
        "Search the web for queries and return structured titles, URLs, and snippets. "
        "Supports concurrent multi-query batching (queries), domain filtering, and recency. "
        "Use to discover external documentation, APIs, and modern libraries (current year is injected via system prompt). "
        "Never use for reading full pages (use webfetch) or searching local files (use grep)."
    )
    capability_id = "web_search"
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_NETWORK
    domains = (TOOL_DOMAIN_WEB,)
    search_terms = (
        "web",
        "search",
        "query",
        "google",
        "bing",
        "brave",
        "tavily",
        "serper",
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
                "query": {
                    "type": "string",
                    "description": "Single search query string (optional if 'queries' is provided)",
                },
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Batch of up to 4 search queries to execute concurrently",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return per query (1-20, default 8)",
                    "default": _DEFAULT_MAX_RESULTS,
                    "minimum": 1,
                    "maximum": 20,
                },
                "allowed_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Restrict results to these domains (e.g. ['github.com', 'docs.python.org'])",
                },
                "blocked_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Exclude results from these domains (e.g. ad networks or aggregators)",
                },
                "recency": {
                    "type": "string",
                    "enum": ["day", "week", "month", "year"],
                    "description": "Optional recency filter to restrict results to fresh content",
                },
            },
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        # Defensive: accept common aliases the model may emit (pattern/q/search)
        # even if param_normalizer was bypassed (native tool_calls, legacy payloads).
        _raw_q = params.get("query")
        if not _raw_q:
            _raw_q = params.get("pattern") or params.get("q") or params.get("search") or ""
        raw_query = str(_raw_q).strip() if _raw_q is not None else ""
        raw_queries = params.get("queries") or params.get("patterns") or params.get("query_list") or []

        query_list: list[str] = []
        if raw_queries and isinstance(raw_queries, list):
            query_list = [str(q).strip() for q in raw_queries if str(q).strip()][:_MAX_QUERY_BATCH_SIZE]
        elif raw_query:
            query_list = [raw_query]

        if not query_list:
            return ToolResult(success=False, error="No search query provided")

        try:
            max_results = min(int(params.get("max_results", _DEFAULT_MAX_RESULTS)), 20)
        except (TypeError, ValueError):
            max_results = _DEFAULT_MAX_RESULTS

        allowed_domains = params.get("allowed_domains") or []
        blocked_domains = params.get("blocked_domains") or []
        recency = params.get("recency")

        api = os.environ.get("ZENITH_SEARCH_API", "").strip().lower()
        key = os.environ.get("ZENITH_SEARCH_API_KEY", "").strip()

        async def _execute_query(q: str) -> tuple[list[dict[str, str]], str]:
            src = "DuckDuckGo"
            if api and key:
                try:
                    res = await self._search_api(
                        api,
                        key,
                        q,
                        max_results,
                        recency=recency,
                        allowed_domains=allowed_domains,
                        blocked_domains=blocked_domains,
                    )
                    src = f"{api} search"
                except ValueError:
                    raise
                except Exception as err:
                    logger.warning(
                        "Search API '%s' failed (%s). Falling back to DuckDuckGo.", api, err
                    )
                    res = await self._search_duckduckgo(q, max_results, recency=recency) if recency else await self._search_duckduckgo(q, max_results)
                    src = "DuckDuckGo (fallback)"
            else:
                res = await self._search_duckduckgo(q, max_results, recency=recency) if recency else await self._search_duckduckgo(q, max_results)
                src = "DuckDuckGo"

            # Domain filtering
            filtered = res
            if allowed_domains:
                domains = {d.lower().lstrip(".") for d in allowed_domains}
                filtered = [
                    r for r in filtered
                    if any(dom in (r.get("url") or "").lower() for dom in domains)
                ][:max_results]

            if blocked_domains:
                b_domains = {d.lower().lstrip(".") for d in blocked_domains}
                filtered = [
                    r for r in filtered
                    if not any(b_dom in (r.get("url") or "").lower() for b_dom in b_domains)
                ][:max_results]

            # Register reference tokens in session cache
            cache = get_web_cache()
            for r in filtered:
                u = r.get("url", "")
                if u:
                    r["ref"] = cache.register_ref(u)

            return filtered, src

        try:
            if len(query_list) == 1:
                results, source = await _execute_query(query_list[0])
                all_results = [(query_list[0], results)]
            else:
                tasks = [_execute_query(q) for q in query_list]
                gathered = await asyncio.gather(*tasks)
                all_results = [(q, res[0]) for q, res in zip(query_list, gathered)]
                source = gathered[0][1] if gathered else "federated"
        except ValueError as val_err:
            raise val_err
        except Exception as e:
            return ToolResult(success=False, error=f"Search failed: {e}")

        # Format output
        total_count = sum(len(res) for _, res in all_results)

        if total_count == 0:
            return ToolResult(
                success=True,
                output="No results found.",
                metadata={
                    "query": query_list[0] if len(query_list) == 1 else None,
                    "queries": query_list if len(query_list) > 1 else None,
                    "source": source,
                    "count": 0,
                    "suggestions": "try a broader query (remove year/site filters), try alternative keywords, or try queries=[...] batch with up to 4 variants",
                },
            )

        if len(query_list) == 1:
            q_str = query_list[0]
            res_items = all_results[0][1]
            lines = [f"Search results for '{q_str}' ({source}):"]
            for i, r in enumerate(res_items, 1):
                ref_id = r.get("ref", "")
                ref_tag = f" [ref: {ref_id}]" if ref_id else ""
                lines.append(f"{i}. {r.get('title') or '(no title)'}{ref_tag}")
                lines.append(f"   {r.get('url') or ''}")
                snippet = (r.get("snippet") or "").strip()
                if snippet:
                    lines.append(f"   {snippet}")
            # Actionable next-step hint: prevents emergent stop before webfetch chaining
            lines.append("")
            lines.append(
                "Next: use webfetch with a URL or [ref: ...] token (e.g. webfetch url=\"ref_doc_1\") "
                "to read the page; for large docs add pattern=\"...\" or start_line/end_line to search inside."
            )

            return ToolResult(
                success=True,
                output="\n".join(lines),
                metadata={
                    "query": q_str,
                    "source": source,
                    "count": len(res_items),
                },
            )

        # Multi-query presentation
        lines = [f"Search results for {len(query_list)} queries ({source}):"]
        for q_idx, (q_str, q_results) in enumerate(all_results, 1):
            lines.append(f"\n### Query {q_idx}: '{q_str}' ({len(q_results)} results)")
            if not q_results:
                lines.append("   (No results found)")
                continue
            for i, r in enumerate(q_results, 1):
                ref_id = r.get("ref", "")
                ref_tag = f" [ref: {ref_id}]" if ref_id else ""
                lines.append(f"{i}. {r.get('title') or '(no title)'}{ref_tag}")
                lines.append(f"   {r.get('url') or ''}")
                snippet = (r.get("snippet") or "").strip()
                if snippet:
                    lines.append(f"   {snippet}")
        lines.append("")
        lines.append(
            "Next: use webfetch with a URL or [ref: ...] token (e.g. webfetch url=\"ref_doc_1\") "
            "to read the page; for large docs add pattern=\"...\" or start_line/end_line to search inside."
        )

        return ToolResult(
            success=True,
            output="\n".join(lines),
            metadata={
                "queries": query_list,
                "source": source,
                "count": total_count,
            },
        )

    # ── backends ─────────────────────────────────────────────────────────────

    async def _search_api(
        self,
        api: str,
        key: str,
        query: str,
        max_results: int,
        recency: str | None = None,
        allowed_domains: list[str] | None = None,
        blocked_domains: list[str] | None = None,
    ) -> list[dict[str, str]]:
        import httpx

        headers = {"User-Agent": DEFAULT_USER_AGENT}
        if api == "tavily":
            url = "https://api.tavily.com/search"
            body: dict[str, Any] = {"api_key": key, "query": query, "max_results": max_results}
            if recency:
                body["time_range"] = recency
            if allowed_domains:
                body["include_domains"] = allowed_domains
            if blocked_domains:
                body["exclude_domains"] = blocked_domains
            async with httpx.AsyncClient(timeout=ZENITH_WEBSEARCH_TIMEOUT) as client:
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
            params: dict[str, Any] = {"q": query, "count": max_results}
            if recency:
                recency_map = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}
                params["freshness"] = recency_map.get(recency, recency)
            async with httpx.AsyncClient(timeout=ZENITH_WEBSEARCH_TIMEOUT) as client:
                data = (await client.get(url, params=params, headers=headers)).json()
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
            body = {"q": query, "num": max_results}
            if recency:
                tbs_map = {"day": "qdr:d", "week": "qdr:w", "month": "qdr:m", "year": "qdr:y"}
                body["tbs"] = tbs_map.get(recency, recency)
            async with httpx.AsyncClient(timeout=ZENITH_WEBSEARCH_TIMEOUT) as client:
                data = (await client.post(url, json=body, headers=headers)).json()
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
            params = {"q": query, "count": max_results}
            if recency:
                bing_map = {"day": "Day", "week": "Week", "month": "Month"}
                if recency in bing_map:
                    params["freshness"] = bing_map[recency]
            async with httpx.AsyncClient(timeout=ZENITH_WEBSEARCH_TIMEOUT) as client:
                data = (await client.get(url, params=params, headers=headers)).json()
            return [
                {
                    "title": r.get("name", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", ""),
                }
                for r in data.get("webPages", {}).get("value", [])[:max_results]
            ]
        if api == "exa":
            url = "https://api.exa.ai/search"
            headers["x-api-key"] = key
            headers["Content-Type"] = "application/json"
            exa_body: dict[str, Any] = {
                "query": query,
                "numResults": max_results,
                "useAutoprompt": True,
            }
            if allowed_domains:
                exa_body["includeDomains"] = allowed_domains
            if blocked_domains:
                exa_body["excludeDomains"] = blocked_domains
            async with httpx.AsyncClient(timeout=ZENITH_WEBSEARCH_TIMEOUT) as client:
                data = (await client.post(url, json=exa_body, headers=headers)).json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("text", "") or r.get("snippet", ""),
                }
                for r in data.get("results", [])[:max_results]
            ]
        raise ValueError(f"Unknown search API '{api}' (expected tavily|brave|serper|bing|exa)")

    async def _search_duckduckgo(
        self, query: str, max_results: int, recency: str | None = None
    ) -> list[dict[str, str]]:
        """No-key fallback: scrape the DuckDuckGo HTML endpoint."""
        import httpx

        url = "https://html.duckduckgo.com/html/"
        headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "text/html"}
        params: dict[str, Any] = {"q": query}
        if recency:
            ddg_map = {"day": "d", "week": "w", "month": "m", "year": "y"}
            if recency in ddg_map:
                params["df"] = ddg_map[recency]
        async with httpx.AsyncClient(
            timeout=ZENITH_WEBSEARCH_TIMEOUT, follow_redirects=True
        ) as client:
            response = await client.get(url, params=params, headers=headers)
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
    for m in re.finditer(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page, re.DOTALL
    ):
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
