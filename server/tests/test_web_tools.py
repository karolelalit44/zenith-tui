"""Tests for the web tools: HTML->Markdown conversion and websearch parsing."""

import pathlib

import pytest

from server.toolkit.tools._html_text import html_to_markdown
from server.toolkit.tools.websearch import WebsearchTool, _parse_ddg_results


class TestHtmlToMarkdown:
    def test_strips_scripts_styles_and_nav(self):
        html = """
        <html><head><title>Ignored</title><style>.x{color:red}</style></head>
        <body>
          <nav><a href="/x">Home</a><a href="/y">Docs</a></nav>
          <script>alert('hi')</script>
          <main><h1>Hello</h1><p>World <b>bold</b>.</p></main>
        </body></html>
        """
        md = html_to_markdown(html)
        assert "Hello" in md
        assert "World bold." in md
        assert "Ignored" not in md
        assert "alert" not in md
        assert ".x{color:red}" not in md
        assert "Home" not in md  # nav skipped

    def test_prefers_main_article_content(self):
        html = """
        <body>
          <div class="sidebar">Sidebar cruft that should not appear</div>
          <article><h2>Real Content</h2><p>Only this matters.</p></article>
          <footer>Footer text</footer>
        </body>
        """
        md = html_to_markdown(html)
        assert "Real Content" in md
        assert "Only this matters." in md
        assert "Sidebar cruft" not in md
        assert "Footer text" not in md

    def test_preserves_code_blocks(self):
        html = "<pre><code>def f():\n    return 1</code></pre>"
        md = html_to_markdown(html)
        assert "def f():" in md
        assert "return 1" in md

    def test_keeps_link_hrefs(self):
        html = '<p>See <a href="https://example.com/docs">the docs</a>.</p>'
        md = html_to_markdown(html)
        assert "the docs" in md
        assert "https://example.com/docs" in md

    def test_malformed_html_does_not_crash(self):
        md = html_to_markdown("<p>unclosed <b>text</p> <div><spam")
        assert isinstance(md, str)

    def test_max_chars_truncates(self):
        html = "<p>" + "a" * 500 + "</p>"
        md = html_to_markdown(html, max_chars=50)
        assert len(md) <= 50

    def test_formats_tables_with_dividers(self):
        html = """
        <table>
          <thead><tr><th>Method</th><th>Description</th></tr></thead>
          <tbody>
            <tr><td>GET</td><td>Retrieve item</td></tr>
            <tr><td>POST</td><td>Create item</td></tr>
          </tbody>
        </table>
        """
        md = html_to_markdown(html)
        assert "| Method | Description |" in md
        assert "| --- | --- |" in md
        assert "| GET | Retrieve item |" in md
        assert "| POST | Create item |" in md

    def test_extracts_code_language_tag(self):
        html = '<pre><code class="language-python">x = 42\nprint(x)</code></pre>'
        md = html_to_markdown(html)
        assert "```python" in md
        assert "x = 42" in md
        assert "```" in md

    def test_resolves_relative_links(self):
        html = '<p>Check <a href="/docs/intro">documentation</a></p>'
        md = html_to_markdown(html, base_url="https://example.com/api/v1")
        assert "[documentation](https://example.com/docs/intro)" in md

    def test_html_to_plain_text(self):
        from server.toolkit.tools._html_text import html_to_plain_text
        html = "<div><h1>Title</h1><p>Paragraph with <a href='#'>link</a>.</p><script>alert('bad')</script></div>"
        text = html_to_plain_text(html)
        assert "Title" in text
        assert "Paragraph with link." in text
        assert "alert" not in text

    def test_extract_images(self):
        from server.toolkit.tools._html_text import extract_images
        html = '<div><img src="/img/arch.png" alt="Architecture Diagram"/><img src="https://cdn.example.com/logo.svg"/></div>'
        imgs = extract_images(html, base_url="https://example.com/page")
        assert len(imgs) == 2
        assert imgs[0]["url"] == "https://example.com/img/arch.png"
        assert imgs[0]["alt"] == "Architecture Diagram"
        assert imgs[1]["url"] == "https://cdn.example.com/logo.svg"


class TestWebsearchParsing:
    def test_parse_ddg_results_unwraps_redirects(self):
        page = """
        <div class="result">
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage%3Fa%3D1&amp;rut=x">
            Example Title
          </a>
          <a class="result__snippet" href="//duckduckgo.com/l/?uddg=...">A short snippet here.</a>
        </div>
        <div class="result">
          <a class="result__a" href="https://direct.example/2">Second Result</a>
        </div>
        """
        results = _parse_ddg_results(page)
        assert len(results) == 2
        assert results[0]["title"] == "Example Title"
        assert results[0]["url"] == "https://example.com/page?a=1"
        assert results[0]["snippet"] == "A short snippet here."
        assert results[1]["url"] == "https://direct.example/2"

    def test_parse_skips_non_http_links(self):
        page = '<a class="result__a" href="#anchor">Anchor</a>'
        assert _parse_ddg_results(page) == []

    @pytest.mark.asyncio
    async def test_empty_query_fails(self):
        tool = WebsearchTool()
        result = await tool.execute({"query": "  "}, ".")
        assert not result.success
        assert "No search query" in result.error


class TestWebsearchExecution:
    """Domain filtering + backend routing + API result parsing for websearch."""

    @pytest.mark.asyncio
    async def test_allowed_domains_filters_results(self, monkeypatch):
        tool = WebsearchTool()

        async def _fake_ddg(query, max_results):
            return [
                {"title": "Match", "url": "https://github.com/foo", "snippet": "x"},
                {"title": "Other", "url": "https://example.com/foo", "snippet": "y"},
            ]

        monkeypatch.setattr(tool, "_search_duckduckgo", _fake_ddg)
        result = await tool.execute({"query": "q", "allowed_domains": ["github.com"]}, ".")
        assert result.success
        assert "https://github.com/foo" in result.output
        assert "https://example.com/foo" not in result.output
        assert result.metadata["count"] == 1

    @pytest.mark.asyncio
    async def test_allowed_domains_empty_result(self, monkeypatch):
        tool = WebsearchTool()

        async def _fake_ddg(query, max_results):
            return [{"title": "A", "url": "https://example.com/x", "snippet": "s"}]

        monkeypatch.setattr(tool, "_search_duckduckgo", _fake_ddg)
        result = await tool.execute({"query": "q", "allowed_domains": ["notthere.io"]}, ".")
        assert result.success
        assert result.output == "No results found."
        assert result.metadata["count"] == 0
        assert "suggestions" in result.metadata

    @pytest.mark.asyncio
    async def test_allowed_domains_case_and_dot_insensitive(self, monkeypatch):
        tool = WebsearchTool()

        async def _fake_ddg(query, max_results):
            return [
                {"title": "A", "url": "https://GitHub.com/x", "snippet": "s"},
            ]

        monkeypatch.setattr(tool, "_search_duckduckgo", _fake_ddg)
        result = await tool.execute({"query": "q", "allowed_domains": [".GITHUB.COM"]}, ".")
        assert result.success
        assert result.metadata["count"] == 1

    @pytest.mark.asyncio
    async def test_max_results_passed_to_backend(self, monkeypatch):
        tool = WebsearchTool()
        seen = {}

        async def _fake_ddg(query, max_results):
            seen["max"] = max_results
            return [{"title": str(i), "url": f"https://e.com/{i}", "snippet": ""} for i in range(6)]

        monkeypatch.setattr(tool, "_search_duckduckgo", _fake_ddg)
        result = await tool.execute({"query": "q", "max_results": 3}, ".")
        assert seen["max"] == 3
        assert result.success
        assert result.metadata["count"] == 6  # backend does the slicing

    @pytest.mark.parametrize(
        "api,response,expected_url",
        [
            (
                "tavily",
                {"results": [{"title": "T", "url": "https://t.co/x", "content": "sn"}]},
                "https://t.co/x",
            ),
            (
                "brave",
                {
                    "web": {
                        "results": [{"title": "B", "url": "https://b.co/x", "description": "sn"}]
                    }
                },
                "https://b.co/x",
            ),
            (
                "serper",
                {"organic": [{"title": "S", "link": "https://s.co/x", "snippet": "sn"}]},
                "https://s.co/x",
            ),
            (
                "bing",
                {"webPages": {"value": [{"name": "G", "url": "https://g.co/x", "snippet": "sn"}]}},
                "https://g.co/x",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_api_backends_parse_results(self, monkeypatch, api, response, expected_url):
        import httpx

        class _Resp:
            def __init__(self, data):
                self._data = data

            def json(self):
                return self._data

        class _FakeClient:
            def __init__(self, *a, **k):
                self._resp = _Resp(response)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

            async def post(self, *a, **k):
                return self._resp

            async def get(self, *a, **k):
                return self._resp

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
        tool = WebsearchTool()
        results = await tool._search_api(api, "key", "query", 5)
        assert results[0]["url"] == expected_url
        assert results[0]["title"] in {"T", "B", "S", "G"}

    @pytest.mark.asyncio
    async def test_unknown_api_raises(self):
        tool = WebsearchTool()
        with pytest.raises(ValueError):
            await tool._search_api("wat", "key", "q", 5)


class TestSsrfGuardIsTheOnlyFetchPath:
    """The SSRF firewall must be the *only* way this module reaches the network.

    A "simple"/"insecure" fetch helper with a default that skips validation is a
    bypass waiting for the next caller, so the invariant is pinned structurally:
    the module builds no HTTP client of its own, and the tool refuses blocked
    targets before any request is attempted.
    """

    def test_module_constructs_no_http_client(self):
        import server.toolkit.tools.webfetch as webfetch_mod

        source = pathlib.Path(webfetch_mod.__file__).read_text(encoding="utf-8")
        assert "AsyncClient" not in source, (
            "webfetch must not build its own HTTP client; all requests go "
            "through secure_fetch, which validates the target"
        )
        assert "follow_redirects=True" not in source, (
            "unguarded redirect following belongs only in _transport, where each "
            "hop is revalidated"
        )

    @pytest.mark.asyncio
    async def test_blocked_targets_are_refused_before_any_request(self, monkeypatch):
        import server.toolkit.tools.webfetch as webfetch_mod

        called = []

        async def _fail(*_a, **_k):
            called.append(1)
            raise AssertionError("network must not be touched for a blocked target")

        monkeypatch.setattr(webfetch_mod, "secure_fetch", _fail)

        for url in (
            "http://127.0.0.1:8080/admin",
            "http://169.254.169.254/latest/meta-data/",
            "http://localhost:3000/",
            "http://10.0.0.5/internal",
        ):
            result = await webfetch_mod.WebfetchTool().execute({"url": url}, ".")
            assert result.success is False, url
            assert "security" in result.error.lower() or "not supported" in result.error.lower()

        assert not called
