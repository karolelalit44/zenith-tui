from __future__ import annotations

import base64
import pytest
from unittest.mock import AsyncMock, patch

from server.toolkit.tools._transport import (
    SSRFSecurityError,
    TransportResponse,
)
from server.toolkit.tools._web_cache import get_web_cache
from server.toolkit.tools.webfetch import FetchResult, WebfetchTool, fetch_page


@pytest.fixture(autouse=True)
def clear_cache():
    get_web_cache().clear()
    yield
    get_web_cache().clear()


class TestWebfetchTool:
    @pytest.mark.asyncio
    async def test_full_document_fetch(self):
        tool = WebfetchTool()
        html_content = "<html><body><main><h1>Header</h1><p>Paragraph content.</p></main></body></html>"
        mock_resp = TransportResponse(
            url="https://example.com/docs",
            status_code=200,
            headers={"content-type": "text/html"},
            content_type="text/html",
            charset="utf-8",
            body_bytes=html_content.encode("utf-8"),
            text=html_content,
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res = await tool.execute({"url": "https://example.com/docs"}, workspace_root=".")
            assert res.success is True
            assert "# Header" in res.output
            assert "Paragraph content." in res.output
            assert res.metadata["url"] == "https://example.com/docs"
            assert res.metadata["ref"].startswith("ref_doc_")

    @pytest.mark.asyncio
    async def test_session_cache_avoids_second_network_fetch(self):
        tool = WebfetchTool()
        html_content = "<h1>Cached Title</h1><p>Line 1\nLine 2\nLine 3</p>"
        mock_resp = TransportResponse(
            url="https://example.com/page",
            status_code=200,
            headers={"content-type": "text/html"},
            content_type="text/html",
            charset="utf-8",
            body_bytes=html_content.encode("utf-8"),
            text=html_content,
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res1 = await tool.execute({"url": "https://example.com/page"}, workspace_root=".")
            assert res1.success is True
            assert mock_fetch.call_count == 1

            # Second fetch should hit cache
            res2 = await tool.execute({"url": "https://example.com/page"}, workspace_root=".")
            assert res2.success is True
            assert mock_fetch.call_count == 1  # Network not called again

            # Fetching by ref_doc_N token also hits cache
            ref_token = res1.metadata["ref"]
            res3 = await tool.execute({"url": ref_token}, workspace_root=".")
            assert res3.success is True
            assert mock_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_line_range_slicing(self):
        tool = WebfetchTool()
        content = "\n".join(f"Line number {i}" for i in range(1, 51))
        mock_resp = TransportResponse(
            url="https://example.com/lines.txt",
            status_code=200,
            headers={"content-type": "text/plain"},
            content_type="text/plain",
            charset="utf-8",
            body_bytes=content.encode("utf-8"),
            text=content,
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res = await tool.execute(
                {"url": "https://example.com/lines.txt", "start_line": 10, "end_line": 15},
                workspace_root=".",
            )
            assert res.success is True
            assert "Showing lines 10-15 of 50 total lines" in res.output
            assert "L10: Line number 10" in res.output
            assert "L15: Line number 15" in res.output
            assert "L9: " not in res.output
            assert "L16: " not in res.output

    @pytest.mark.asyncio
    async def test_line_range_invalid_order_fails(self):
        tool = WebfetchTool()
        content = "Line 1\nLine 2"
        mock_resp = TransportResponse(
            url="https://example.com/lines.txt",
            status_code=200,
            headers={"content-type": "text/plain"},
            content_type="text/plain",
            charset="utf-8",
            body_bytes=content.encode("utf-8"),
            text=content,
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res = await tool.execute(
                {"url": "https://example.com/lines.txt", "start_line": 20, "end_line": 5},
                workspace_root=".",
            )
            assert res.success is False
            assert "Invalid line range" in res.error

    @pytest.mark.asyncio
    async def test_in_page_pattern_search(self):
        tool = WebfetchTool()
        lines = [
            "Introduction",
            "Setup guide",
            "Configuring database",
            "FATAL_ERROR: connection refused at port 5432",
            "Retrying in 5 seconds",
            "Cleanup",
        ]
        content = "\n".join(lines)
        mock_resp = TransportResponse(
            url="https://example.com/log.txt",
            status_code=200,
            headers={"content-type": "text/plain"},
            content_type="text/plain",
            charset="utf-8",
            body_bytes=content.encode("utf-8"),
            text=content,
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res = await tool.execute(
                {"url": "https://example.com/log.txt", "pattern": "connection refused", "context_lines": 1},
                workspace_root=".",
            )
            assert res.success is True
            assert "Found 1 match(es)" in res.output
            assert ">>> L4: FATAL_ERROR: connection refused" in res.output
            assert "L3: Configuring database" in res.output
            assert "L5: Retrying in 5 seconds" in res.output

    @pytest.mark.asyncio
    async def test_in_page_pattern_search_no_matches(self):
        tool = WebfetchTool()
        content = "Some normal lines\nAnother line"
        mock_resp = TransportResponse(
            url="https://example.com/page",
            status_code=200,
            headers={"content-type": "text/plain"},
            content_type="text/plain",
            charset="utf-8",
            body_bytes=content.encode("utf-8"),
            text=content,
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res = await tool.execute(
                {"url": "https://example.com/page", "pattern": "nonexistent_term"},
                workspace_root=".",
            )
            assert res.success is True
            assert "No matches found for pattern 'nonexistent_term'" in res.output

    @pytest.mark.asyncio
    async def test_visible_truncation_contract(self):
        tool = WebfetchTool()
        long_body = ("Paragraph line with some text.\n" * 100).strip()
        mock_resp = TransportResponse(
            url="https://example.com/long",
            status_code=200,
            headers={"content-type": "text/plain"},
            content_type="text/plain",
            charset="utf-8",
            body_bytes=long_body.encode("utf-8"),
            text=long_body,
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res = await tool.execute(
                {"url": "https://example.com/long", "max_chars": 1000},
                workspace_root=".",
            )
            assert res.success is True
            assert res.metadata["truncated"] is True
            assert "[TRUNCATION NOTICE: Content truncated at" in res.output
            assert "re-invoke webfetch with start_line and end_line parameters" in res.output

    @pytest.mark.asyncio
    async def test_ssrf_blocked_returns_security_error(self):
        tool = WebfetchTool()
        with patch("server.toolkit.tools.webfetch.secure_fetch", side_effect=SSRFSecurityError("Access to 127.0.0.1 is blocked")):
            res = await tool.execute({"url": "http://127.0.0.1/admin"}, workspace_root=".")
            assert res.success is False
            assert "Security error" in res.error
            assert "127.0.0.1" in res.error

    @pytest.mark.asyncio
    async def test_unsupported_binary_pdf_fails(self):
        tool = WebfetchTool()
        mock_resp = TransportResponse(
            url="https://example.com/manual.pdf",
            status_code=200,
            headers={"content-type": "application/pdf"},
            content_type="application/pdf",
            charset="utf-8",
            body_bytes=b"%PDF-1.4 binary data",
            text="%PDF-1.4 binary data",
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res = await tool.execute({"url": "https://example.com/manual.pdf"}, workspace_root=".")
            assert res.success is False
            assert "Unsupported binary document format" in res.error

    @pytest.mark.asyncio
    async def test_image_returns_base64_multimodal(self):
        tool = WebfetchTool()
        raw_img = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        mock_resp = TransportResponse(
            url="https://example.com/diagram.png",
            status_code=200,
            headers={"content-type": "image/png"},
            content_type="image/png",
            charset="utf-8",
            body_bytes=raw_img,
            text="",
            is_image=True,
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res = await tool.execute({"url": "https://example.com/diagram.png"}, workspace_root=".")
            assert res.success is True
            assert res.metadata["is_image"] is True
            assert res.metadata["base64"] == base64.b64encode(raw_img).decode("ascii")
            assert "Image fetched successfully" in res.output
            assert "data:image/png;base64," in res.output

    @pytest.mark.asyncio
    async def test_invalid_scheme_fails(self):
        tool = WebfetchTool()
        res = await tool.execute({"url": "file:///etc/passwd"}, workspace_root=".")
        assert res.success is False
        assert "Only http/https URLs are supported" in res.error
