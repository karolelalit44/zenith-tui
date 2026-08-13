"""Dependency-free HTML -> readable Markdown conversion for web tools.

Converts fetched HTML into clean, compact Markdown so the model never has to
consume raw markup. Mirrors the industry-standard approach (Claude Code converts
server-side HTML to Markdown before the model sees it).

Design:
- Skips script/style/nav/header/footer/aside/svg/form/iframe/etc.
- When the page has a <main>, <article>, or role="main" element, only that
  subtree is extracted (preference for the actual content over chrome).
- Preserves code blocks verbatim and keeps link hrefs.
"""

from __future__ import annotations

import html as _html
import re
from html.parser import HTMLParser

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
        "title",
        "head",
        "figure",
        "figcaption",
    }
)
_HEADING_TAGS = frozenset(f"h{i}" for i in range(1, 7))
_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "section",
        "main",
        "article",
        "ul",
        "ol",
        "li",
        "pre",
        "blockquote",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "td",
        "th",
        "hr",
        "br",
        "address",
        "details",
        "summary",
        "fieldset",
        "dl",
        "dt",
        "dd",
        "form",
    }
)
_CODE_TAGS = frozenset({"pre", "code", "kbd", "samp", "tt"})


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.buf: list[str] = []
        self._depth = 0
        self._skip = 0
        self._pre = 0
        self._root_depth: int | None = None  # depth where main/article opened
        self._root_closed = False
        self._pending_link: str | None = None

    def _emit(self, text: str) -> None:
        if self._skip or self._root_closed:
            return
        if self._root_depth is not None and self._depth < self._root_depth:
            return
        self.buf.append(text)

    def _newline(self) -> None:
        self._emit("\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._depth += 1
        attr_map = dict(attrs)
        if tag in _SKIP_TAGS:
            self._skip += 1
            return
        if self._root_depth is None and not self._root_closed:
            if tag in ("main", "article") or attr_map.get("role") == "main":
                self._root_depth = self._depth
                # Content before the root (nav/sidebar/header) is not part of
                # the page body — drop anything emitted so far.
                self.buf = []
        if tag in _CODE_TAGS:
            self._pre += 1
        if tag in _HEADING_TAGS:
            self._newline()
            self._emit("#" * int(tag[1]) + " ")
        elif tag in _BLOCK_TAGS:
            self._newline()
            if tag == "li":
                self._emit("- ")
            elif tag in ("dt", "dd"):
                self._emit("* ")
            elif tag == "tr":
                self._emit("| ")
        elif tag == "a":
            self._pending_link = attr_map.get("href") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            if self._skip:
                self._skip -= 1
            self._depth -= 1
            return
        if tag in _CODE_TAGS and self._pre:
            self._pre -= 1
        if (
            tag in ("main", "article")
            and self._root_depth is not None
            and self._depth == self._root_depth
        ):
            self._root_closed = True
        if tag in _HEADING_TAGS or tag in _BLOCK_TAGS:
            self._newline()
        elif tag == "a" and self._pending_link:
            self._emit(f" ({self._pending_link})")
            self._pending_link = None
        self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._pre or data.strip():
            self._emit(data)

    def result(self) -> str:
        text = "".join(self.buf)
        text = _html.unescape(text)
        # Collapse runs of blank lines, trim trailing space per line.
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_markdown(html: str, max_chars: int | None = None) -> str:
    parser = _Extractor()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        # Never let a malformed page take down the tool; fall back to a raw
        # text dump rather than raising.
        text = re.sub(r"<[^>]+>", " ", html or "")
        return re.sub(r"\s+", " ", _html.unescape(text)).strip()[: max_chars or 0] or text
    text = parser.result()
    if max_chars and len(text) > max_chars:
        text = text[:max_chars]
    return text
