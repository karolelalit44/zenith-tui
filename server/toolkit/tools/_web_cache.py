from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import time
import urllib.parse

_DEFAULT_MAX_DOCUMENTS = 20


@dataclass
class CachedDocument:
    """Cached representation of a fetched web document."""

    url: str
    ref_id: str
    content_type: str
    chars: int
    markdown: str
    lines: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    is_image: bool = False
    base64_data: str | None = None

    @property
    def total_lines(self) -> int:
        return len(self.lines)


class WebDocumentCache:
    """Session-scoped LRU cache for fetched web documents and search result references.

    Enables line-slicing and in-page pattern search without re-fetching pages
    from the network.
    """

    def __init__(self, max_documents: int = _DEFAULT_MAX_DOCUMENTS) -> None:
        self.max_documents = max_documents
        self._cache: OrderedDict[str, CachedDocument] = OrderedDict()
        self._ref_to_url: dict[str, str] = {}
        self._url_to_ref: dict[str, str] = {}
        self._next_ref_index: int = 1

    def _normalize_url(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url.strip())
        return urllib.parse.urlunparse(
            (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", "", "")
        )

    def register_ref(self, url: str) -> str:
        """Assign or retrieve a reference token (e.g. 'ref_doc_1') for a URL."""
        norm = self._normalize_url(url)
        if norm in self._url_to_ref:
            return self._url_to_ref[norm]
        ref_id = f"ref_doc_{self._next_ref_index}"
        self._next_ref_index += 1
        self._url_to_ref[norm] = ref_id
        self._ref_to_url[ref_id] = norm
        return ref_id

    def resolve_url(self, query: str) -> str:
        """Resolve a URL or reference token (ref_doc_N, doc_N, [ref: doc_N]) to a canonical URL."""
        clean = query.strip()
        if clean.startswith("[ref:") and clean.endswith("]"):
            clean = clean[5:-1].strip()
        if clean.startswith("ref_") or clean.startswith("doc_"):
            ref_key = clean if clean.startswith("ref_") else f"ref_{clean}"
            if ref_key in self._ref_to_url:
                return self._ref_to_url[ref_key]
        return clean

    def get(self, url_or_ref: str) -> CachedDocument | None:
        resolved_url = self.resolve_url(url_or_ref)
        norm = self._normalize_url(resolved_url)
        if norm in self._cache:
            doc = self._cache[norm]
            self._cache.move_to_end(norm)
            return doc
        return None

    def put(
        self,
        url: str,
        content_type: str,
        markdown: str,
        chars: int | None = None,
        is_image: bool = False,
        base64_data: str | None = None,
    ) -> CachedDocument:
        norm = self._normalize_url(url)
        ref_id = self.register_ref(url)
        lines = markdown.splitlines()
        doc = CachedDocument(
            url=url,
            ref_id=ref_id,
            content_type=content_type,
            chars=chars if chars is not None else len(markdown),
            markdown=markdown,
            lines=lines,
            timestamp=time.time(),
            is_image=is_image,
            base64_data=base64_data,
        )
        if norm in self._cache:
            self._cache.move_to_end(norm)
        self._cache[norm] = doc
        while len(self._cache) > self.max_documents:
            self._cache.popitem(last=False)
        return doc

    def clear(self) -> None:
        """Clear all cached entries and reference tokens."""
        self._cache.clear()
        self._ref_to_url.clear()
        self._url_to_ref.clear()
        self._next_ref_index = 1


_GLOBAL_WEB_CACHE = WebDocumentCache()


def get_web_cache() -> WebDocumentCache:
    """Return the global session web document cache."""
    return _GLOBAL_WEB_CACHE
