from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from server.toolkit.tools._web_cache import get_web_cache
from server.toolkit.tools.websearch import WebsearchTool


@pytest.fixture(autouse=True)
def clear_cache():
    get_web_cache().clear()
    yield
    get_web_cache().clear()


class TestWebsearchAdvanced:
    @pytest.mark.asyncio
    async def test_multi_query_concurrent_execution(self, monkeypatch):
        tool = WebsearchTool()

        async def _fake_ddg(query, max_results):
            if "pydantic" in query:
                return [
                    {"title": "Pydantic V2 Guide", "url": "https://docs.pydantic.dev/2", "snippet": "Pydantic snippet"}
                ]
            return [
                {"title": "FastAPI Lifespan", "url": "https://fastapi.tiangolo.com/lifespan", "snippet": "FastAPI snippet"}
            ]

        monkeypatch.setattr(tool, "_search_duckduckgo", _fake_ddg)
        res = await tool.execute(
            {"queries": ["pydantic v2", "fastapi lifespan"]},
            workspace_root=".",
        )

        assert res.success is True
        assert "Search results for 2 queries" in res.output
        assert "### Query 1: 'pydantic v2'" in res.output
        assert "### Query 2: 'fastapi lifespan'" in res.output
        assert "https://docs.pydantic.dev/2" in res.output
        assert "https://fastapi.tiangolo.com/lifespan" in res.output
        assert res.metadata["count"] == 2

        # Check reference tokens registered in cache
        cache = get_web_cache()
        doc_pydantic_url = cache.resolve_url("ref_doc_1")
        assert "pydantic.dev" in doc_pydantic_url

    @pytest.mark.asyncio
    async def test_provider_fallback_to_duckduckgo_on_api_error(self, monkeypatch):
        tool = WebsearchTool()
        monkeypatch.setenv("ZENITH_SEARCH_API", "tavily")
        monkeypatch.setenv("ZENITH_SEARCH_API_KEY", "test-key")

        async def _fail_api(*args, **kwargs):
            raise RuntimeError("API rate limited or server error")

        async def _fallback_ddg(query, max_results):
            return [{"title": "Fallback Result", "url": "https://ddg.example/1", "snippet": "Found via fallback"}]

        monkeypatch.setattr(tool, "_search_api", _fail_api)
        monkeypatch.setattr(tool, "_search_duckduckgo", _fallback_ddg)

        res = await tool.execute({"query": "python async"}, workspace_root=".")
        assert res.success is True
        assert "DuckDuckGo (fallback)" in res.output
        assert "https://ddg.example/1" in res.output
        assert res.metadata["source"] == "DuckDuckGo (fallback)"

    @pytest.mark.asyncio
    async def test_blocked_domains_filters_results(self, monkeypatch):
        tool = WebsearchTool()

        async def _fake_ddg(query, max_results):
            return [
                {"title": "Legit Docs", "url": "https://docs.python.org/3", "snippet": "Python docs"},
                {"title": "Ad Aggregator", "url": "https://spam-scraper.com/bad", "snippet": "Scraped"},
            ]

        monkeypatch.setattr(tool, "_search_duckduckgo", _fake_ddg)
        res = await tool.execute(
            {"query": "python", "blocked_domains": ["spam-scraper.com"]},
            workspace_root=".",
        )
        assert res.success is True
        assert "https://docs.python.org/3" in res.output
        assert "https://spam-scraper.com/bad" not in res.output
        assert res.metadata["count"] == 1

    @pytest.mark.asyncio
    async def test_exa_api_backend_parsing(self, monkeypatch):
        import httpx

        class _Resp:
            def __init__(self, data):
                self._data = data

            def json(self):
                return self._data

        class _FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

            async def post(self, *a, **k):
                return _Resp({
                    "results": [
                        {"title": "Exa Neural Match", "url": "https://exa.example/match", "text": "Neural snippet"}
                    ]
                })

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
        tool = WebsearchTool()
        results = await tool._search_api("exa", "exa-key", "neural search", 5)
        assert len(results) == 1
        assert results[0]["title"] == "Exa Neural Match"
        assert results[0]["url"] == "https://exa.example/match"
        assert results[0]["snippet"] == "Neural snippet"
