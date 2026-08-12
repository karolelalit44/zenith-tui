"""Tests for the web tools: HTML->Markdown conversion and websearch parsing."""

import pytest

from server.toolkit.tools._html_text import html_to_markdown
from server.toolkit.tools.webfetch import WebfetchTool
from server.toolkit.tools.websearch import WebsearchTool, _parse_ddg_results


class _FakeProvider:
    """Minimal stand-in for LLMProvider.complete(messages, model=None)."""

    def __init__(self, answer: str = "fake answer"):
        self.answer = answer
        self.last_messages = None
        self.last_model = None

    async def complete(self, messages, tools=None, model=None):
        self.last_messages = messages
        self.last_model = model
        return self.answer


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


class TestWebfetchExtraction:
    @pytest.mark.asyncio
    async def test_extract_answer_uses_provider(self):
        provider = _FakeProvider(answer="Claude Code has WebSearch and WebFetch tools.")
        tool = WebfetchTool(provider=provider)
        answer = await tool._extract_answer("Some page body content", "What tools does it have?")
        assert answer == "Claude Code has WebSearch and WebFetch tools."
        assert provider.last_messages is not None
        assert "What tools does it have?" in provider.last_messages[0]["content"]
        assert "Some page body content" in provider.last_messages[0]["content"]

    @pytest.mark.asyncio
    async def test_extract_answer_none_on_provider_error(self):
        class _Raising:
            async def complete(self, messages, tools=None, model=None):
                raise RuntimeError("boom")

        tool = WebfetchTool(provider=_Raising())
        assert await tool._extract_answer("body", "q") is None

    @pytest.mark.asyncio
    async def test_extract_with_provider_returns_answer(self, monkeypatch):
        import httpx

        class _Resp:
            headers = {"content-type": "text/html"}
            text = "<html><body><main><p>Claude Code ships WebSearch and WebFetch.</p></main></body></html>"

            def raise_for_status(self):
                return None

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

            async def get(self, url):
                return _Resp()

        monkeypatch.setattr(httpx, "AsyncClient", _Client)
        provider = _FakeProvider(answer="WebSearch + WebFetch.")
        tool = WebfetchTool(provider=provider)
        result = await tool.execute({"url": "https://example.com", "extract": "What tools?"}, ".")
        assert result.success
        assert result.output == "WebSearch + WebFetch."
        assert result.metadata.get("extracted") is True

    @pytest.mark.asyncio
    async def test_extract_without_provider_notes_fallback(self, monkeypatch):
        import httpx

        class _Resp:
            headers = {"content-type": "text/html"}
            text = "<html><body><main><p>Some body.</p></main></body></html>"

            def raise_for_status(self):
                return None

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

            async def get(self, url):
                return _Resp()

        monkeypatch.setattr(httpx, "AsyncClient", _Client)
        tool = WebfetchTool()  # no provider
        result = await tool.execute({"url": "https://example.com", "extract": "What?"}, ".")
        assert result.success
        assert "no model is available" in result.output
        assert "Some body." in result.output
