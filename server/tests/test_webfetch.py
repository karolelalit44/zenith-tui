from __future__ import annotations

import base64
from unittest.mock import AsyncMock, patch

import pytest

from server.toolkit.tools._transport import (
    SSRFSecurityError,
    TransportResponse,
)
from server.toolkit.tools._web_cache import get_web_cache
from server.toolkit.tools.webfetch import WebfetchTool


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
    async def test_pdf_with_text_extraction(self):
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

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch, \
             patch("server.toolkit.tools.webfetch._extract_pdf_text", return_value="## Page 1\n\nPDF content extracted."):
            mock_fetch.return_value = mock_resp
            res = await tool.execute({"url": "https://example.com/manual.pdf"}, workspace_root=".")
            assert res.success is True
            assert "PDF content extracted." in res.output
            assert res.metadata["url"] == "https://example.com/manual.pdf"

    @pytest.mark.asyncio
    async def test_pdf_without_text_prompts_download(self):
        tool = WebfetchTool()
        mock_resp = TransportResponse(
            url="https://example.com/scanned.pdf",
            status_code=200,
            headers={"content-type": "application/pdf"},
            content_type="application/pdf",
            charset="utf-8",
            body_bytes=b"%PDF-1.4 scanned data",
            text="",
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch, \
             patch("server.toolkit.tools.webfetch._extract_pdf_text", return_value=""):
            mock_fetch.return_value = mock_resp
            res = await tool.execute({"url": "https://example.com/scanned.pdf"}, workspace_root=".")
            assert res.success is True
            assert "contains no extractable text" in res.output
            assert "download_path='scanned.pdf'" in res.output
            assert res.metadata["is_pdf"] is True

    @pytest.mark.asyncio
    async def test_download_pdf_to_file(self, tmp_path):
        tool = WebfetchTool()
        pdf_bytes = b"%PDF-1.4 valid pdf content"
        mock_resp = TransportResponse(
            url="https://example.com/docs/manual.pdf",
            status_code=200,
            headers={"content-type": "application/pdf"},
            content_type="application/pdf",
            charset="utf-8",
            body_bytes=pdf_bytes,
            text="",
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res = await tool.execute(
                {"url": "https://example.com/docs/manual.pdf", "download_path": "docs/output.pdf"},
                workspace_root=str(tmp_path),
            )
            assert res.success is True
            assert "Successfully downloaded" in res.output
            assert res.metadata["downloaded"] is True
            assert res.metadata["path"] == "docs/output.pdf"
            saved_file = tmp_path / "docs" / "output.pdf"
            assert saved_file.exists()
            assert saved_file.read_bytes() == pdf_bytes

    @pytest.mark.asyncio
    async def test_download_image_to_file(self, tmp_path):
        tool = WebfetchTool()
        img_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        mock_resp = TransportResponse(
            url="https://example.com/logo.png",
            status_code=200,
            headers={"content-type": "image/png"},
            content_type="image/png",
            charset="utf-8",
            body_bytes=img_bytes,
            text="",
            is_image=True,
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res = await tool.execute(
                {"url": "https://example.com/logo.png", "download_path": "assets/logo.png"},
                workspace_root=str(tmp_path),
            )
            assert res.success is True
            assert res.metadata["downloaded"] is True
            assert (tmp_path / "assets" / "logo.png").read_bytes() == img_bytes

    @pytest.mark.asyncio
    async def test_download_audio_and_video_to_file(self, tmp_path):
        tool = WebfetchTool()
        audio_bytes = b"ID3\x03\x00\x00\x00"
        mock_audio = TransportResponse(
            url="https://example.com/sound.mp3",
            status_code=200,
            headers={"content-type": "audio/mpeg"},
            content_type="audio/mpeg",
            charset="utf-8",
            body_bytes=audio_bytes,
            text="",
        )
        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_audio
            res = await tool.execute(
                {"url": "https://example.com/sound.mp3", "download_path": "media/sound.mp3"},
                workspace_root=str(tmp_path),
            )
            assert res.success is True
            assert (tmp_path / "media" / "sound.mp3").read_bytes() == audio_bytes

    @pytest.mark.asyncio
    async def test_download_in_active_session_evicts_cache_and_journals(self, tmp_path):
        from server.toolkit.journal import JOURNAL
        from server.toolkit.registry import current_tool_session_id

        tool = WebfetchTool()
        mock_resp = TransportResponse(
            url="https://example.com/doc.pdf",
            status_code=200,
            headers={"content-type": "application/pdf"},
            content_type="application/pdf",
            charset="utf-8",
            body_bytes=b"%PDF-test",
            text="",
        )

        sid = "sess-webfetch-test"
        JOURNAL.clear(sid)
        token = current_tool_session_id.set(sid)
        try:
            with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = mock_resp
                res = await tool.execute(
                    {"url": "https://example.com/doc.pdf", "download_path": "doc.pdf"},
                    workspace_root=str(tmp_path),
                )
                assert res.success is True
                assert (tmp_path / "doc.pdf").read_bytes() == b"%PDF-test"
                entries = JOURNAL.entries(sid)
                assert len(entries) == 1
                assert entries[0].tool == "webfetch"
                assert entries[0].action == "create"
                assert entries[0].after == b"%PDF-test"
        finally:
            current_tool_session_id.reset(token)
            JOURNAL.clear(sid)

    @pytest.mark.asyncio
    async def test_download_to_directory_infers_filename(self, tmp_path):
        tool = WebfetchTool()
        mock_resp = TransportResponse(
            url="https://example.com/archive.zip",
            status_code=200,
            headers={"content-type": "application/zip"},
            content_type="application/zip",
            charset="utf-8",
            body_bytes=b"PK\x03\x04zipdata",
            text="",
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res = await tool.execute(
                {"url": "https://example.com/archive.zip", "download_path": "downloads/"},
                workspace_root=str(tmp_path),
            )
            assert res.success is True
            assert res.metadata["path"] == "downloads/archive.zip"
            assert (tmp_path / "downloads" / "archive.zip").exists()

    @pytest.mark.asyncio
    async def test_download_already_exists_fails_without_overwrite(self, tmp_path):
        tool = WebfetchTool()
        dest = tmp_path / "existing.pdf"
        dest.write_bytes(b"initial")

        mock_resp = TransportResponse(
            url="https://example.com/existing.pdf",
            status_code=200,
            headers={"content-type": "application/pdf"},
            content_type="application/pdf",
            charset="utf-8",
            body_bytes=b"new data",
            text="",
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            # 1. Fails without overwrite
            res = await tool.execute(
                {"url": "https://example.com/existing.pdf", "download_path": "existing.pdf", "overwrite": False},
                workspace_root=str(tmp_path),
            )
            assert res.success is False
            assert "already exists" in res.error

            # 2. Succeeds with overwrite=True
            res2 = await tool.execute(
                {"url": "https://example.com/existing.pdf", "download_path": "existing.pdf", "overwrite": True},
                workspace_root=str(tmp_path),
            )
            assert res2.success is True
            assert dest.read_bytes() == b"new data"

    @pytest.mark.asyncio
    async def test_download_path_escaping_workspace_blocked(self, tmp_path):
        tool = WebfetchTool()
        mock_resp = TransportResponse(
            url="https://example.com/hack.sh",
            status_code=200,
            headers={"content-type": "application/octet-stream"},
            content_type="application/octet-stream",
            charset="utf-8",
            body_bytes=b"payload",
            text="",
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res = await tool.execute(
                {"url": "https://example.com/hack.sh", "download_path": "../../evil.sh"},
                workspace_root=str(tmp_path),
            )
            assert res.success is False
            assert "escapes workspace boundary" in res.error

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

    @pytest.mark.asyncio
    async def test_audio_fetch_without_download_path(self):
        tool = WebfetchTool()
        mock_resp = TransportResponse(
            url="https://example.com/podcast.mp3",
            status_code=200,
            headers={"content-type": "audio/mpeg"},
            content_type="audio/mpeg",
            charset="utf-8",
            body_bytes=b"fake-mp3-bytes",
            text="",
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res = await tool.execute({"url": "https://example.com/podcast.mp3"}, workspace_root=".")
            assert res.success is True
            assert res.metadata["is_audio"] is True
            assert "Audio content fetched successfully" in res.output
            assert "podcast.mp3" in res.output

    @pytest.mark.asyncio
    async def test_video_fetch_without_download_path(self):
        tool = WebfetchTool()
        mock_resp = TransportResponse(
            url="https://example.com/trailer.mp4",
            status_code=200,
            headers={"content-type": "video/mp4"},
            content_type="video/mp4",
            charset="utf-8",
            body_bytes=b"fake-mp4-bytes",
            text="",
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res = await tool.execute({"url": "https://example.com/trailer.mp4"}, workspace_root=".")
            assert res.success is True
            assert res.metadata["is_video"] is True
            assert "Video content fetched successfully" in res.output
            assert "trailer.mp4" in res.output

    @pytest.mark.asyncio
    async def test_archive_fetch_without_download_path(self):
        tool = WebfetchTool()
        mock_resp = TransportResponse(
            url="https://example.com/data.tar.gz",
            status_code=200,
            headers={"content-type": "application/gzip"},
            content_type="application/gzip",
            charset="utf-8",
            body_bytes=b"fake-tar-bytes",
            text="",
        )

        with patch("server.toolkit.tools.webfetch.secure_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            res = await tool.execute({"url": "https://example.com/data.tar.gz"}, workspace_root=".")
            assert res.success is True
            assert res.metadata["is_binary"] is True
            assert "Binary archive/content fetched successfully" in res.output

    @pytest.mark.asyncio
    async def test_plan_mode_guard_blocks_download_of_non_plan_files(self):
        from server.config.constants import PLAN_MODE
        from server.toolkit.base import ToolContext
        from server.toolkit.middleware.plan_write import PlanWriteGuard

        guard = PlanWriteGuard()
        ctx = ToolContext(
            request_id="test",
            session_id="test",
            workspace_root="/workspace",
            mode=PLAN_MODE,
            tool_name="webfetch",
        )
        res = await guard.before_execute("webfetch", {"url": "https://example.com/doc.pdf", "download_path": "doc.pdf"}, ctx)
        assert res is not True
        assert res.success is False
        assert "Plan mode only allows writing plan.md or todo.md" in res.error

    @pytest.mark.asyncio
    async def test_read_only_guard_blocks_webfetch_download(self):
        from server.config.constants import READ_ONLY_MODE
        from server.toolkit.base import ToolContext
        from server.toolkit.middleware.read_only import ReadOnlyModeGuard
        from server.toolkit.registry import ToolRegistry

        registry = ToolRegistry()
        guard = ReadOnlyModeGuard(registry)
        ctx = ToolContext(
            request_id="test",
            session_id="test",
            workspace_root="/workspace",
            mode=READ_ONLY_MODE,
            tool_name="webfetch",
        )
        res = await guard.before_execute("webfetch", {"url": "https://example.com/doc.pdf", "download_path": "doc.pdf"}, ctx)
        assert res is not True
        assert res.success is False
        assert "investigation is strictly read-only" in res.error

