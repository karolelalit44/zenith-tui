"""Dependency-free HTML -> readable Markdown & text conversion for web tools.

Transforms fetched HTML into clean, semantic Markdown and plain text so the model
receives structured information without markup noise.

Design:
- Excludes script, style, noscript, template, svg, iframe, form, nav, header, footer, aside.
- Prioritizes semantic main content subtrees (<main>, <article>, role="main", .markdown-body).
- Formats GitHub-Flavored Markdown tables with aligned pipes and divider rows.
- Formats pre/code blocks as fenced code blocks with language detection.
- Emits clean markdown links [text](url), resolving relative URLs against base_url.
- Extracts images for multimodal inspection.
"""

from __future__ import annotations

import html as _html
import re
import urllib.parse
from html.parser import HTMLParser
from typing import Any

_SKIP_TAGS = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "iframe",
        "frame",
        "frameset",
        "form",
        "button",
        "select",
        "option",
        "optgroup",
        "textarea",
        "input",
        "label",
        "nav",
        "header",
        "footer",
        "aside",
        "dialog",
        "picture",
        "source",
        "track",
        "audio",
        "video",
        "canvas",
        "map",
        "area",
        "embed",
        "object",
        "param",
        "link",
        "meta",
        "base",
        "head",
    }
)

_HEADING_TAGS = frozenset(f"h{i}" for i in range(1, 7))
_CODE_TAGS = frozenset({"pre", "code", "kbd", "samp", "tt"})


class _MarkdownExtractor(HTMLParser):
    def __init__(self, base_url: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.buf: list[str] = []
        self._depth = 0
        self._skip = 0
        self._pre = False
        self._pre_needs_open = False
        self._code_lang: str | None = None
        self._root_depth: int | None = None
        self._root_closed = False

        # Link tracking
        self._link_href: str | None = None
        self._link_text_buf: list[str] = []

        # List tracking
        self._list_stack: list[dict[str, Any]] = []

        # Table tracking
        self._in_table = False
        self._in_header = False
        self._current_row: list[str] = []
        self._current_cell: list[str] = []
        self._table_rows: list[tuple[bool, list[str]]] = []  # (is_header, cells)

        # Blockquote tracking
        self._blockquote_depth = 0

    def _emit(self, text: str) -> None:
        if self._skip or self._root_closed:
            return
        if self._root_depth is not None and self._depth < self._root_depth:
            return

        if self._link_href is not None:
            self._link_text_buf.append(text)
            return

        if self._in_table:
            self._current_cell.append(text)
            return

        self.buf.append(text)

    def _newline(self, count: int = 1) -> None:
        if self._skip or self._root_closed:
            return
        if self._in_table or self._link_href is not None:
            return
        self._emit("\n" * count)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._depth += 1
        attr_map = dict(attrs)

        if tag in _SKIP_TAGS:
            self._skip += 1
            return

        # Main content root discovery
        if self._root_depth is None and not self._root_closed:
            cls = (attr_map.get("class") or "").lower()
            elem_id = (attr_map.get("id") or "").lower()
            role = (attr_map.get("role") or "").lower()

            is_main = (
                tag in ("main", "article")
                or role == "main"
                or any(k in cls for k in ("main-content", "article-body", "post-content", "markdown-body"))
                or any(k in elem_id for k in ("main-content", "article-body", "post-content"))
            )
            if is_main:
                self._root_depth = self._depth
                # Content before main content is usually noise
                self.buf = []

        # Headings
        if tag in _HEADING_TAGS:
            self._newline(2)
            level = int(tag[1])
            self._emit("#" * level + " ")

        # Block containers
        elif tag == "p":
            self._newline(2)

        elif tag == "blockquote":
            self._blockquote_depth += 1
            self._newline(2)
            self._emit("> ")

        elif tag in ("ul", "ol"):
            self._newline()
            self._list_stack.append({"type": tag, "index": 1})

        elif tag == "li":
            self._newline()
            indent = "  " * max(0, len(self._list_stack) - 1)
            if self._list_stack and self._list_stack[-1]["type"] == "ol":
                idx = self._list_stack[-1]["index"]
                self._emit(f"{indent}{idx}. ")
                self._list_stack[-1]["index"] += 1
            else:
                self._emit(f"{indent}- ")

        elif tag == "pre":
            self._pre = True
            self._pre_needs_open = True
            self._newline(2)
            cls = attr_map.get("class") or ""
            m = re.search(r"(?:lang|language)-([a-zA-Z0-9_-]+)", cls)
            self._code_lang = m.group(1) if m else None

        elif tag == "code":
            if not self._pre:
                self._emit("`")
            else:
                if self._code_lang is None:
                    cls = attr_map.get("class") or ""
                    m = re.search(r"(?:lang|language)-([a-zA-Z0-9_-]+)", cls)
                    if m:
                        self._code_lang = m.group(1)
                if self._pre_needs_open:
                    self.buf.append(f"```{self._code_lang or ''}\n")
                    self._pre_needs_open = False

        elif tag == "table":
            self._in_table = True
            self._table_rows = []
            self._newline(2)

        elif tag == "thead":
            self._in_header = True

        elif tag == "tr":
            self._current_row = []

        elif tag in ("th", "td"):
            self._current_cell = []

        elif tag == "hr":
            self._newline(2)
            self._emit("---\n")

        elif tag == "br":
            self._newline()

        elif tag == "a":
            raw_href = attr_map.get("href") or ""
            if raw_href and not raw_href.startswith("javascript:"):
                if self.base_url and not raw_href.startswith(("http://", "https://", "mailto:", "#")):
                    self._link_href = urllib.parse.urljoin(self.base_url, raw_href)
                else:
                    self._link_href = raw_href
            else:
                self._link_href = None
            self._link_text_buf = []

        elif tag == "img":
            src = attr_map.get("src") or ""
            alt = attr_map.get("alt") or "image"
            if src and not src.startswith("data:"):
                if self.base_url and not src.startswith(("http://", "https://")):
                    src = urllib.parse.urljoin(self.base_url, src)
                self._emit(f"![{alt}]({src})")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            if self._skip:
                self._skip -= 1
            self._depth -= 1
            return

        if self._root_depth is not None and self._depth == self._root_depth:
            self._root_closed = True

        if tag in _HEADING_TAGS or tag == "p":
            self._newline(2)

        elif tag == "blockquote":
            if self._blockquote_depth > 0:
                self._blockquote_depth -= 1
            self._newline(2)

        elif tag in ("ul", "ol"):
            if self._list_stack:
                self._list_stack.pop()
            self._newline()

        elif tag == "pre":
            if self._pre_needs_open:
                self.buf.append(f"```{self._code_lang or ''}\n")
                self._pre_needs_open = False
            self._pre = False
            self._code_lang = None
            self._emit("\n```\n")

        elif tag == "code":
            if not self._pre:
                self._emit("`")

        elif tag == "thead":
            self._in_header = False

        elif tag in ("th", "td"):
            cell_text = "".join(self._current_cell).replace("\n", " ").strip()
            self._current_row.append(cell_text)
            self._current_cell = []

        elif tag == "tr":
            if self._current_row:
                self._table_rows.append((self._in_header, self._current_row))
            self._current_row = []

        elif tag == "table":
            self._in_table = False
            self._render_table()

        elif tag == "a":
            link_text = "".join(self._link_text_buf).strip()
            href = self._link_href
            self._link_href = None
            self._link_text_buf = []

            if href:
                if link_text:
                    self.buf.append(f"[{link_text}]({href})")
                else:
                    self.buf.append(f"<{href}>")
            elif link_text:
                self.buf.append(link_text)

        self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._pre:
            if self._pre_needs_open:
                self.buf.append(f"```{self._code_lang or ''}\n")
                self._pre_needs_open = False
            self._emit(data)
        elif data.strip() or data == " ":
            self._emit(data)

    def _render_table(self) -> None:
        if not self._table_rows:
            return

        col_count = max(len(row[1]) for row in self._table_rows)
        if col_count == 0:
            return

        rendered_lines = []
        has_header = any(r[0] for r in self._table_rows)

        # If no explicit thead, treat the first row as header if there are multiple rows
        first_row_header = has_header or len(self._table_rows) > 1

        for i, (is_hdr, cells) in enumerate(self._table_rows):
            padded_cells = cells + [""] * (col_count - len(cells))
            row_str = "| " + " | ".join(padded_cells) + " |"
            rendered_lines.append(row_str)

            if i == 0 and first_row_header:
                divider = "| " + " | ".join(["---"] * col_count) + " |"
                rendered_lines.append(divider)

        self.buf.append("\n" + "\n".join(rendered_lines) + "\n\n")

    def result(self) -> str:
        text = "".join(self.buf)
        text = _html.unescape(text)

        # Normalize line breaks and multiple consecutive spaces
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_markdown(html: str, max_chars: int | None = None, base_url: str = "") -> str:
    """Convert HTML string to clean, structured Markdown."""
    if not html:
        return ""
    parser = _MarkdownExtractor(base_url=base_url)
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # Fallback to robust regex tag stripping on parser failure
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", _html.unescape(text)).strip()[: max_chars or 0] or text

    text = parser.result()
    if max_chars and len(text) > max_chars:
        text = text[:max_chars]
    return text


def html_to_plain_text(html: str, max_chars: int | None = None) -> str:
    """Fast, dependency-free HTML -> plain text converter for ultra-compact token consumption."""
    if not html:
        return ""
    # Strip script/style blocks completely
    cleaned = re.sub(r"<(script|style|noscript|template)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Convert block start and end tags to newlines
    cleaned = re.sub(r"</?(p|div|h[1-6]|li|tr|td|th|ul|ol|table|blockquote|pre|br|hr)[^>]*>", "\n", cleaned, flags=re.IGNORECASE)
    # Strip all remaining inline tags without injecting artificial spaces
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    text = _html.unescape(cleaned)
    # Collapse intra-line whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if max_chars and len(text) > max_chars:
        text = text[:max_chars]
    return text


def extract_images(html: str, base_url: str = "") -> list[dict[str, str]]:
    """Extract image URLs and their alt descriptions from HTML."""
    if not html:
        return []
    images: list[dict[str, str]] = []
    pattern = re.compile(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)
    alt_pattern = re.compile(r'alt=["\']([^"\']*)["\']', re.IGNORECASE)

    for m in pattern.finditer(html):
        src = m.group(1).strip()
        if not src or src.startswith("data:"):
            continue
        if base_url and not src.startswith(("http://", "https://")):
            src = urllib.parse.urljoin(base_url, src)

        tag_full = m.group(0)
        alt_match = alt_pattern.search(tag_full)
        alt = alt_match.group(1).strip() if alt_match else ""
        images.append({"url": src, "alt": alt})

    return images
