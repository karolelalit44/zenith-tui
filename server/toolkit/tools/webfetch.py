from __future__ import annotations

import base64
import io
import logging
import mimetypes
import os
import re
import urllib.parse
from typing import Any

from server.agents.session_workspace import evict_read_cache_path, record_write
from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    COST_CLASS_MEDIUM,
    DEFAULT_WEBDOWNLOAD_MAX_BYTES,
    FILE_ALREADY_EXISTS_ERROR,
    LATENCY_CLASS_HIGH,
    RISK_LOW,
    TOOL_DOMAIN_WEB,
    is_http_url,
)
from server.config.environment import (
    ZENITH_WEBDOWNLOAD_MAX_BYTES,
    ZENITH_WEBFETCH_MAX_BYTES,
)
from server.toolkit.path_validator import validate_path
from server.toolkit.registry import current_tool_session_id
from server.workspace.ignore import blocked_as_missing, get_matcher, mutation_refusal

from ..base import BaseTool, ToolResult
from ..journal import JOURNAL
from ._html_text import html_to_markdown, html_to_plain_text
from ._transport import (
    MAX_PAYLOAD_BYTES,
    PayloadTooLargeError,
    RedirectSecurityError,
    SSRFSecurityError,
    TransportSecurityError,
    secure_fetch,
    validate_url_target,
)
from ._web_cache import CachedDocument, get_web_cache

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CHARS = ZENITH_WEBFETCH_MAX_BYTES
_DEFAULT_MAX_DOWNLOAD_BYTES = ZENITH_WEBDOWNLOAD_MAX_BYTES or DEFAULT_WEBDOWNLOAD_MAX_BYTES

_MIME_EXTENSIONS: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "application/gzip": ".tar.gz",
    "application/x-tar": ".tar",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "text/html": ".html",
    "text/markdown": ".md",
    "text/plain": ".txt",
    "application/json": ".json",
}


def infer_download_filename(
    url: str,
    headers: dict[str, str] | None = None,
    content_type: str = "",
) -> str:
    headers = headers or {}
    cd = headers.get("content-disposition") or headers.get("Content-Disposition") or ""
    filename = ""
    if cd:
        fn_match = re.search(r"filename\*\s*=\s*(?:UTF-8''|utf-8'')?([^;]+)", cd, re.IGNORECASE)
        if fn_match:
            filename = urllib.parse.unquote(fn_match.group(1).strip(" \"'"))
        else:
            fn_match = re.search(r'filename\s*=\s*"?([^";]+)"?', cd, re.IGNORECASE)
            if fn_match:
                filename = fn_match.group(1).strip()

    if not filename:
        parsed = urllib.parse.urlsplit(url)
        path = parsed.path.rstrip("/")
        if path:
            candidate = os.path.basename(path)
            candidate = urllib.parse.unquote(candidate)
            if candidate:
                filename = candidate

    clean_mime = content_type.split(";")[0].strip().lower()
    ext = _MIME_EXTENSIONS.get(clean_mime) or mimetypes.guess_extension(clean_mime) or ""
    if not filename:
        filename = f"download{ext}"
    elif ext and not os.path.splitext(filename)[1]:
        filename = f"{filename}{ext}"

    filename = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", filename).strip(". ")
    if not filename or filename.upper() in ("CON", "PRN", "AUX", "NUL", "COM1", "COM2", "LPT1"):
        filename = f"downloaded_file{ext}"
    return filename


def _extract_pdf_text(data: bytes) -> str:
    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(data))
        parts: list[str] = []
        for i, page in enumerate(reader.pages):
            txt = (page.extract_text() or "").strip()
            if txt:
                parts.append(f"## Page {i + 1}\n\n{txt}")
        return "\n\n".join(parts)
    except Exception as e:
        logger.debug("PDF text extraction failed: %s", e)
        return ""


# Every outbound request in this module goes through ``secure_fetch`` in
# ``_transport``, which validates the target against blocked subnets before the
# request and again on every redirect hop. There is deliberately no second,
# "simple" fetch path and no flag to opt out of validation: a bypass that is only
# reachable by passing an argument is a bypass that eventually gets passed.


class WebfetchTool(BaseTool):
    name = "webfetch"
    description = (
        "Fetch a web URL to inspect its content in clean Markdown or text, or download files "
        "(PDF, image, audio, video, archives, datasets, or any web resource) directly to the workspace "
        "using 'download_path'. Supports targeted line slicing (start_line, end_line) and in-page "
        "pattern search (pattern). Never use for local files (use file_read)."
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
        "download_file",
        "pdf",
        "image",
        "audio",
        "video",
        "media",
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
                        "URL to fetch or download (http/https only) or reference token (e.g. 'ref_doc_1')"
                    ),
                },
                "download_path": {
                    "type": "string",
                    "description": (
                        "Workspace-relative file or directory path where fetched content should be saved "
                        "(e.g. 'downloads/report.pdf', 'assets/image.png', 'audio/track.mp3', 'video/clip.mp4'). "
                        "If a directory is specified (or ends with '/'), the filename is inferred from URL or headers."
                    ),
                },
                "download": {
                    "type": "boolean",
                    "description": (
                        "If true, forces saving the fetched content to disk. If download_path is omitted, "
                        "saves to the workspace using an inferred filename from the URL."
                    ),
                    "default": False,
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "If true, overwrites an existing file at download_path. Defaults to false.",
                    "default": False,
                },
                "max_bytes": {
                    "type": "integer",
                    "description": "Maximum payload bytes allowed to download/fetch (defaults to 100MB for downloads)",
                    "minimum": 1000,
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

        # Validate on every request, before the cache is consulted. A cache hit
        # performs no network I/O, so this is not about the fetch — it is that a
        # document which entered the cache while its target was reachable must
        # stop being served the moment that stops being true (DNS rebound to
        # loopback, a host re-pointed at the metadata endpoint). The cache is a
        # content store, never an authority on whether a target is allowed.
        try:
            await validate_url_target(resolved_url)
        except SSRFSecurityError as e:
            return ToolResult(success=False, error=f"Security error: {e}")
        except ValueError as e:
            return ToolResult(success=False, error=f"Invalid URL: {e}")

        # Check if download is requested
        download_path = (
            params.get("download_path")
            or params.get("save_path")
            or params.get("output_path")
            or (params.get("path") if params.get("url") != params.get("path") else None)
        )
        download_flag = bool(params.get("download", False))
        is_download = bool(download_path or download_flag)
        overwrite = bool(params.get("overwrite", False))

        max_bytes_param = params.get("max_bytes")
        try:
            max_payload_bytes = (
                int(max_bytes_param)
                if max_bytes_param is not None
                else (_DEFAULT_MAX_DOWNLOAD_BYTES if is_download else MAX_PAYLOAD_BYTES)
            )
        except (TypeError, ValueError):
            max_payload_bytes = _DEFAULT_MAX_DOWNLOAD_BYTES if is_download else MAX_PAYLOAD_BYTES

        doc: CachedDocument | None = cache.get(resolved_url)
        as_text = bool(params.get("as_text", False))

        body_bytes: bytes | None = doc.raw_bytes if (doc and doc.raw_bytes) else None
        content_type: str = doc.content_type if doc else ""
        headers: dict[str, str] = doc.headers if doc else {}
        resp_url: str = doc.url if doc else resolved_url

        if body_bytes is None:
            try:
                resp = await secure_fetch(
                    resolved_url,
                    format="binary" if is_download else "markdown",
                    max_payload_bytes=max_payload_bytes,
                )
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

            body_bytes = resp.body_bytes
            content_type = resp.content_type
            headers = resp.headers
            resp_url = resp.url

        # Handle file download if requested
        if is_download:
            if download_path:
                dp = str(download_path).strip()
                validated_existing = validate_path(dp, workspace_root)
                if dp.endswith(("/", "\\")) or (validated_existing and validated_existing.is_dir()):
                    fname = infer_download_filename(resp_url, headers, content_type)
                    rel_target = os.path.join(dp, fname).replace("\\", "/")
                else:
                    rel_target = dp
            else:
                fname = infer_download_filename(resp_url, headers, content_type)
                rel_target = fname

            resolved_target = validate_path(rel_target, workspace_root)
            if resolved_target is None:
                return ToolResult(
                    success=False,
                    error=f"Path escapes workspace boundary: {rel_target}. Use relative paths within the project.",
                )

            if blocked_as_missing(get_matcher(workspace_root), rel_target):
                return ToolResult(success=False, error=mutation_refusal(rel_target))

            existed = resolved_target.exists()
            if existed and not overwrite:
                return ToolResult(
                    success=False,
                    error=FILE_ALREADY_EXISTS_ERROR.format(
                        path=rel_target, overwrite_param="overwrite"
                    ),
                )

            before_bytes: bytes | None = None
            if existed:
                try:
                    before_bytes = resolved_target.read_bytes()
                except OSError:
                    before_bytes = None

            try:
                resolved_target.parent.mkdir(parents=True, exist_ok=True)
                resolved_target.write_bytes(body_bytes)
            except OSError as e:
                return ToolResult(
                    success=False,
                    error=f"Failed to write downloaded content to '{rel_target}': {e}",
                )

            session_id = current_tool_session_id.get()
            if session_id:
                evict_read_cache_path(str(resolved_target))
                try:
                    text_summary = body_bytes.decode("utf-8")
                except Exception:
                    text_summary = f"<binary {content_type} {len(body_bytes)} bytes>"
                record_write(session_id, rel_target, text_summary)
                JOURNAL.record(
                    session_id,
                    tool="webfetch",
                    path=resolved_target,
                    action="modify" if existed else "create",
                    before=before_bytes,
                    after=body_bytes,
                    extra={"url": resp_url},
                )

            doc = cache.put(
                url=resp_url,
                content_type=content_type,
                markdown=f"# Downloaded: {rel_target}\n\n- Source: {resp_url}\n- Size: {len(body_bytes)} bytes\n- Content-Type: {content_type}",
                chars=len(body_bytes),
                raw_bytes=body_bytes,
                headers=headers,
            )

            return ToolResult(
                success=True,
                output=(
                    f"Successfully downloaded {resp_url} to '{rel_target}' "
                    f"({content_type}, {len(body_bytes)} bytes)."
                ),
                metadata={
                    "url": resp_url,
                    "path": rel_target,
                    "bytes": len(body_bytes),
                    "content_type": content_type,
                    "downloaded": True,
                    "ref": doc.ref_id,
                },
            )

        # If document not yet in cache, process and populate cache
        if doc is None:
            # Multimodal image handling
            if content_type.startswith("image/"):
                b64 = base64.b64encode(body_bytes).decode("ascii")
                data_uri = f"data:{content_type};base64,{b64}"
                doc = cache.put(
                    url=resp_url,
                    content_type=content_type,
                    markdown=f"![Image]({resp_url})",
                    chars=len(body_bytes),
                    is_image=True,
                    base64_data=data_uri,
                    raw_bytes=body_bytes,
                    headers=headers,
                )
                suggested = infer_download_filename(resp_url, headers, content_type)
                return ToolResult(
                    success=True,
                    output=(
                        f"Image fetched successfully ({content_type}, {len(body_bytes)} bytes).\n"
                        f"Data URI: {data_uri[:100]}... [total base64 length: {len(b64)}]\n"
                        f"To save this image to workspace, re-invoke with download_path='{suggested}'."
                    ),
                    metadata={
                        "url": resp_url,
                        "content_type": content_type,
                        "is_image": True,
                        "base64": b64,
                        "bytes": len(body_bytes),
                        "ref": doc.ref_id,
                    },
                )

            # Audio handling
            if content_type.startswith("audio/"):
                doc = cache.put(
                    url=resp_url,
                    content_type=content_type,
                    markdown=f"# Audio File: {resp_url} ({len(body_bytes)} bytes)",
                    chars=len(body_bytes),
                    raw_bytes=body_bytes,
                    headers=headers,
                )
                suggested = infer_download_filename(resp_url, headers, content_type)
                return ToolResult(
                    success=True,
                    output=(
                        f"Audio content fetched successfully ({content_type}, {len(body_bytes)} bytes).\n"
                        f"To save this audio file to workspace, re-invoke with download_path='audio/{suggested}'."
                    ),
                    metadata={
                        "url": resp_url,
                        "content_type": content_type,
                        "bytes": len(body_bytes),
                        "is_audio": True,
                        "ref": doc.ref_id,
                    },
                )

            # Video handling
            if content_type.startswith("video/"):
                doc = cache.put(
                    url=resp_url,
                    content_type=content_type,
                    markdown=f"# Video File: {resp_url} ({len(body_bytes)} bytes)",
                    chars=len(body_bytes),
                    raw_bytes=body_bytes,
                    headers=headers,
                )
                suggested = infer_download_filename(resp_url, headers, content_type)
                return ToolResult(
                    success=True,
                    output=(
                        f"Video content fetched successfully ({content_type}, {len(body_bytes)} bytes).\n"
                        f"To save this video file to workspace, re-invoke with download_path='video/{suggested}'."
                    ),
                    metadata={
                        "url": resp_url,
                        "content_type": content_type,
                        "bytes": len(body_bytes),
                        "is_video": True,
                        "ref": doc.ref_id,
                    },
                )

            # PDF handling
            if content_type == "application/pdf" or resp_url.lower().endswith(".pdf"):
                pdf_text = _extract_pdf_text(body_bytes)
                suggested = infer_download_filename(resp_url, headers, content_type)
                if pdf_text.strip():
                    doc = cache.put(
                        url=resp_url,
                        content_type=content_type,
                        markdown=pdf_text,
                        chars=len(pdf_text),
                        raw_bytes=body_bytes,
                        headers=headers,
                    )
                else:
                    doc = cache.put(
                        url=resp_url,
                        content_type=content_type,
                        markdown=f"# PDF Document: {resp_url} ({len(body_bytes)} bytes)\n\n(No extractable text)",
                        chars=len(body_bytes),
                        raw_bytes=body_bytes,
                        headers=headers,
                    )
                    return ToolResult(
                        success=True,
                        output=(
                            f"PDF document fetched ({content_type}, {len(body_bytes)} bytes), "
                            "but contains no extractable text. "
                            f"To download the PDF to disk, re-invoke with download_path='{suggested}'."
                        ),
                        metadata={
                            "url": resp_url,
                            "content_type": content_type,
                            "bytes": len(body_bytes),
                            "is_pdf": True,
                            "ref": doc.ref_id,
                        },
                    )

            # Other binary formats (archives, executables, octet-stream, etc.)
            elif any(
                b in content_type
                for b in (
                    "application/zip",
                    "application/gzip",
                    "application/octet-stream",
                    "application/x-tar",
                    "application/x-rar",
                    "application/x-7z-compressed",
                )
            ):
                suggested = infer_download_filename(resp_url, headers, content_type)
                doc = cache.put(
                    url=resp_url,
                    content_type=content_type,
                    markdown=f"# Binary File: {resp_url} ({content_type}, {len(body_bytes)} bytes)",
                    chars=len(body_bytes),
                    raw_bytes=body_bytes,
                    headers=headers,
                )
                return ToolResult(
                    success=True,
                    output=(
                        f"Binary archive/content fetched successfully ({content_type}, {len(body_bytes)} bytes).\n"
                        f"To save this file to workspace, re-invoke with download_path='{suggested}'."
                    ),
                    metadata={
                        "url": resp_url,
                        "content_type": content_type,
                        "bytes": len(body_bytes),
                        "is_binary": True,
                        "ref": doc.ref_id,
                    },
                )
            else:
                # HTML, Markdown, or plain text
                try:
                    text_str = body_bytes.decode("utf-8")
                except Exception:
                    text_str = body_bytes.decode("utf-8", errors="replace")

                if "html" in content_type or content_type in ("text/html", "application/xhtml+xml"):
                    markdown = (
                        html_to_plain_text(text_str)
                        if as_text
                        else html_to_markdown(text_str, base_url=resp_url)
                    )
                else:
                    markdown = text_str

                doc = cache.put(
                    url=resp_url,
                    content_type=content_type,
                    markdown=markdown,
                    chars=len(text_str),
                    raw_bytes=body_bytes,
                    headers=headers,
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

            start_line = max(start_line, 1)
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
                f"({sum(len(line_item) for line_item in sliced)} characters):\n\n"
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
