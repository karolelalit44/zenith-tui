
from __future__ import annotations
from typing import Any
from ..base import BaseTool, ToolResult


class LspDiagnosticsTool(BaseTool):
    name = "lsp_diagnostics"
    description = "Get LSP diagnostics for file"

    def get_schema(self) -> dict:
        return {"type": "object", "properties": {"filepath": {"type": "string", "description": "File path"}}, "required": ["filepath"]}

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        from pathlib import Path
        from server.lsp.manager import get_lsp_manager

        filepath = params.get("filepath", "")
        if not filepath:
            return ToolResult(success=False, error="No filepath provided")

        path = Path(filepath)
        if not path.is_absolute():
            path = Path(workspace_root) / path
        path = path.resolve()

        if not path.exists():
            return ToolResult(success=False, error=f"File not found: {filepath}")

        manager = get_lsp_manager()
        if manager is None:
            return ToolResult(success=False, error="LSP manager not initialized. LSP integration is not available.")

        client = await manager.get_client(str(path))
        if client is None:
            ext = path.suffix
            return ToolResult(success=False, error=f"No LSP server available for '{ext}' files. Install the appropriate language server (e.g., pyright, typescript-language-server, gopls).")

        content = path.read_text(encoding="utf-8", errors="replace")
        try:
            diagnostics = await client.get_diagnostics(str(path), content)
        except Exception as e:
            return ToolResult(success=False, error=f"LSP diagnostics request failed: {e}")

        if not diagnostics:
            return ToolResult(success=True, output=f"No diagnostics for {path.name}", metadata={"diagnostics": [], "server": client.name})

        lines = [f"Found {len(diagnostics)} diagnostic(s) in {path.name} ({client.name}):"]
        for d in diagnostics:
            range_info = d.get("range", {})
            start = range_info.get("start", {})
            line_num = start.get("line", 0) + 1
            col = start.get("character", 0) + 1
            severity = d.get("severity", "unknown")
            message = d.get("message", "")
            source = d.get("source", "")
            prefix = f"[{source}] " if source else ""
            lines.append(f"  {severity.upper()} {path.name}:{line_num}:{col} {prefix}{message}")

        output = "\n".join(lines)
        return ToolResult(success=True, output=output, metadata={"diagnostics": diagnostics, "count": len(diagnostics), "server": client.name})
