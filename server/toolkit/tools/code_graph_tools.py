"""WP6 — structural query tools for the Apogee crewmate.

Single-call answers to relational questions ("who calls X?", "what breaks if Y
changes?") that previously required multi-hop grep chains. Read-only, bounded
outputs, evidence-carrying (file:line) so findings stay verifiable.
"""

from __future__ import annotations

from typing import Any

from server.config.constants import (
    CODE_BLAST_RADIUS_TOOL,
    CODE_CALLERS_TOOL,
    CODE_OUTLINE_TOOL,
    CONCURRENCY_GROUP_READONLY,
    GRAPH_QUERY_MAX_RESULTS,
    GRAPH_QUERY_MAX_OUTPUT_CHARS,
    PERMISSION_READ,
    TOOL_DOMAIN_READ,
)
from server.workspace.graph_queries import get_code_graph

from ..base import BaseTool, ToolResult


def _bounded(lines: list[str]) -> str:
    out = "\n".join(lines).strip()
    if not out:
        return "No matches found."
    if len(out) > GRAPH_QUERY_MAX_OUTPUT_CHARS:
        out = out[: GRAPH_QUERY_MAX_OUTPUT_CHARS - 3].rstrip() + "..."
        out += "\n[truncated — narrow with a more specific symbol]"
    return out


class _CodeGraphTool(BaseTool):
    """Shared plumbing for the structural query family."""

    requires_mode = None
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_READ
    domains = (TOOL_DOMAIN_READ,)
    capability_id = "workspace_discovery"

    def _graph(self, workspace_root: str):
        return get_code_graph(workspace_root)


class CodeCallersTool(_CodeGraphTool):
    name = CODE_CALLERS_TOOL
    description = (
        "Find where a symbol is referenced: returns file:line usage sites "
        "(excluding its definition). One call replaces grep-hop chains for "
        "'who uses this?'. For literal strings inside comments/strings, use grep instead."
    )
    search_terms = ("callers", "usages", "references", "who calls", "symbol")

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Identifier name, e.g. 'run_crewmate'"},
                "max_results": {
                    "type": "integer",
                    "default": GRAPH_QUERY_MAX_RESULTS,
                    "description": "Cap on returned usage sites",
                },
            },
            "required": ["symbol"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        symbol = str(params.get("symbol") or "").strip()
        if not symbol:
            return ToolResult(success=False, error="No symbol provided")
        try:
            max_results = max(
                1, min(int(params.get("max_results") or GRAPH_QUERY_MAX_RESULTS), 100)
            )
        except (TypeError, ValueError):
            max_results = GRAPH_QUERY_MAX_RESULTS

        sites = self._graph(workspace_root).callers(symbol, max_results=max_results)
        if not sites:
            return ToolResult(
                success=True,
                output=f"No references found for '{symbol}' in indexed source files.",
                metadata={"count": 0},
            )
        lines = [
            f"{site['file']}:{site['line']}" if site["line"] else site["file"] for site in sites
        ]
        return ToolResult(
            success=True,
            output=_bounded([f"References of {symbol} ({len(sites)} shown):", *lines]),
            metadata={"count": len(sites), "symbol": symbol},
        )


class CodeOutlineTool(_CodeGraphTool):
    name = CODE_OUTLINE_TOOL
    description = (
        "List a file's definitions (functions/classes/types) with line numbers — "
        "a one-call table of contents. Use before reading a large file."
    )
    search_terms = ("outline", "definitions", "table of contents", "symbols in file")

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Workspace-relative file path, e.g. 'server/agents/loop.py'",
                },
            },
            "required": ["path"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        rel_path = str(params.get("path") or "").strip()
        if not rel_path:
            return ToolResult(success=False, error="No path provided")
        defs = self._graph(workspace_root).outline(rel_path)
        if not defs:
            return ToolResult(
                success=True,
                output=f"No indexable definitions found in {rel_path}.",
                metadata={"count": 0},
            )
        lines = [f"{d['line']:>5}  {d['name']}" for d in defs]
        return ToolResult(
            success=True,
            output=_bounded([f"Definitions in {rel_path}:", *lines]),
            metadata={"count": len(defs), "path": rel_path},
        )


class CodeBlastRadiusTool(_CodeGraphTool):
    name = CODE_BLAST_RADIUS_TOOL
    description = (
        "Impact analysis for a symbol: direct caller sites and the full set of "
        "files a change would touch. Call BEFORE proposing edits to shared code."
    )
    search_terms = ("blast radius", "impact", "affected files", "what breaks")

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Identifier name to analyze"},
            },
            "required": ["symbol"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        symbol = str(params.get("symbol") or "").strip()
        if not symbol:
            return ToolResult(success=False, error="No symbol provided")
        radius = self._graph(workspace_root).blast_radius(symbol)
        callers = radius["direct_callers"]
        affected = radius["affected_files"]
        lines = [
            f"Blast radius of {symbol}: {radius['caller_count']} calling file(s).",
        ]
        if callers:
            lines.append("Direct call sites:")
            lines.extend(
                f"{c['file']}:{c['line']}" if c["line"] else c["file"] for c in callers[:10]
            )
        if affected:
            lines.append("Affected files: " + ", ".join(affected[:12]))
        else:
            lines.append("No callers found — likely safe to change (verify dynamically).")
        return ToolResult(
            success=True,
            output=_bounded(lines),
            metadata={
                "symbol": symbol,
                "caller_count": radius["caller_count"],
                "affected_files": affected[:12],
            },
        )
