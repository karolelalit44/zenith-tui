"""WP6 — structural queries over the workspace symbol graph.

Definitions come from :class:`server.workspace.repo_map.RepoMap` (tree-sitter,
mtime-cached, precise lines). References are backfilled by identifier scan —
mirroring Aider's approach for grammars whose query files carry no
``name.reference`` captures (ours are definition-only today). Every result
carries ``file:line`` so the calling model verifies with one targeted read,
consistent with the evidence rule governing reports.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from server.config.constants import (
    BRIEF_CACHE_TTL_SECONDS,
    EXPLORE_BRIEF_TOP_SYMBOLS,
    GRAPH_QUERY_MAX_RESULTS,
)

logger = logging.getLogger(__name__)

# Identifiers worth indexing: long enough to be meaningful, so stopword noise
# never enters the scan regex.
_MIN_IDENT_LEN = 5


class CodeGraph:
    """Relational lookups over the workspace's tree-sitter symbol graph."""

    def __init__(self, workspace_root: str | Path) -> None:
        from server.workspace.repo_map import RepoMap

        self._root = Path(workspace_root).resolve()
        self._repo_map = RepoMap(str(self._root))
        self._defines: dict[str, set[str]] | None = None
        # ident -> {file: [first ref lines]}
        self._references: dict[str, dict[str, list[int]]] | None = None

    # ------------------------------------------------------------------ #
    # construction                                                        #
    # ------------------------------------------------------------------ #

    def _def_lines(self, rel_file: str) -> dict[str, set[int]]:
        out: dict[str, set[int]] = {}
        try:
            for s in self._repo_map._extract_symbols(self._root / rel_file):
                if s["kind"] == "def":
                    out.setdefault(s["name"], set()).add(s["line"] + 1)
        except Exception as e:
            logger.debug("Def extraction failed for %s: %s", rel_file, e)
        return out

    def _ensure(self) -> tuple[dict[str, set[str]], dict[str, dict[str, list[int]]]]:
        """Build defines (tree-sitter) and backfilled references (scan) once."""
        if self._defines is not None and self._references is not None:
            return self._defines, self._references
        defines: dict[str, set[str]] = {}
        file_defs: dict[str, dict[str, set[int]]] = {}
        try:
            files = self._repo_map._list_files()
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("File listing failed for %s: %s", self._root, e)
            files = []
        rel_files: list[tuple[str, Path]] = []
        for f in files:
            try:
                rel = f.relative_to(self._root).as_posix()
            except ValueError:
                continue
            rel_files.append((rel, f))
            fd = self._def_lines(rel)
            if fd:
                file_defs[rel] = fd
                for ident in fd:
                    defines.setdefault(ident, set()).add(rel)
        idents = sorted(i for i in defines if len(i) >= _MIN_IDENT_LEN)
        references: dict[str, dict[str, list[int]]] = {i: {} for i in idents}
        if idents:
            pattern = re.compile(r"\b(" + "|".join(re.escape(i) for i in idents) + r")\b")
            # Scan EVERY file: usage-only files (no definitions) still count.
            for rel, f in rel_files:
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                fd = file_defs.get(rel, {})
                for match in pattern.finditer(text):
                    ident = match.group(1)
                    line = text.count("\n", 0, match.start()) + 1
                    def_lines = fd.get(ident)
                    if def_lines and line in def_lines:
                        continue  # the definition itself, not a usage
                    slots = references[ident].setdefault(rel, [])
                    if len(slots) < 2:
                        slots.append(line)
        self._defines, self._references = defines, references
        return defines, references

    # ------------------------------------------------------------------ #
    # public queries                                                      #
    # ------------------------------------------------------------------ #

    def callers(self, symbol: str, max_results: int = GRAPH_QUERY_MAX_RESULTS) -> list[dict]:
        """Files referencing ``symbol`` with their first usage lines."""
        _, references = self._ensure()
        sites = references.get(symbol) or {}
        out: list[dict] = []
        for rel in sorted(sites):
            for line in sites[rel]:
                out.append({"file": rel, "line": line})
                if len(out) >= max_results:
                    return out
        return out

    def outline(self, rel_path: str, max_results: int = GRAPH_QUERY_MAX_RESULTS) -> list[dict]:
        """Definitions inside one workspace-relative file."""
        candidate = (self._root / rel_path).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError:
            return []
        if not candidate.is_file():
            return []
        defs = self._def_lines(candidate.relative_to(self._root).as_posix())
        flat = [
            {"name": name, "kind": "def", "line": line}
            for name, lines in sorted(defs.items())
            for line in sorted(lines)
        ]
        return flat[:max_results]

    def blast_radius(self, symbol: str, max_results: int = GRAPH_QUERY_MAX_RESULTS) -> dict:
        """Direct callers of ``symbol`` plus the file set a change would touch."""
        callers = self.callers(symbol, max_results=max_results)
        affected = sorted({c["file"] for c in callers})
        return {
            "symbol": symbol,
            "direct_callers": callers,
            "affected_files": affected,
            "caller_count": len(affected),
        }

    def top_symbols(self, limit: int = EXPLORE_BRIEF_TOP_SYMBOLS) -> list[tuple[str, int]]:
        """Most-referenced identifiers — hub symbols for orientation briefs."""
        _, references = self._ensure()
        ranked = sorted(
            (
                (name, sum(len(lines) for lines in sites.values()))
                for name, sites in references.items()
            ),
            key=lambda kv: (-kv[1], kv[0]),
        )
        return ranked[:limit]


_graph_cache: dict[str, tuple[float, CodeGraph]] = {}


def get_code_graph(workspace_root: str | Path) -> CodeGraph:
    """TTL-cached graph per workspace root (cheap rebuilds, fresh enough)."""
    key = str(Path(workspace_root).resolve())
    now = time.monotonic()
    cached = _graph_cache.get(key)
    if cached and (now - cached[0]) < BRIEF_CACHE_TTL_SECONDS:
        return cached[1]
    graph = CodeGraph(key)
    _graph_cache[key] = (now, graph)
    return graph


def clear_code_graph_cache() -> None:
    _graph_cache.clear()
