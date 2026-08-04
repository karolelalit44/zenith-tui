
from __future__ import annotations
from typing import Any
from ..base import BaseTool, ToolResult


class LspDefinitionTool(BaseTool):
    name = "lsp_definition"
    description = "Go to symbol definition"

    def get_schema(self) -> dict:
        return {"type": "object", "properties": {"filepath": {"type": "string", "description": "File path"}, "line": {"type": "integer", "description": "Line (0-indexed)"}, "character": {"type": "integer", "description": "Column (0-indexed)"}}, "required": ["filepath", "line", "character"]}

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        from pathlib import Path
        from server.lsp.manager import get_lsp_manager

        filepath = params.get("filepath", "")
        line = params.get("line", 0)
        character = params.get("character", 0)

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
            return ToolResult(success=False, error="LSP manager not initialized.")

        client = await manager.get_client(str(path))
        if client is None:
            ext = path.suffix
            return ToolResult(success=False, error=f"No LSP server available for '{ext}' files.")

        content = path.read_text(encoding="utf-8", errors="replace")
        try:
            definitions = await client.goto_definition(str(path), content, line, character)
        except Exception as e:
            return ToolResult(success=False, error=f"LSP definition request failed: {e}")

        if not definitions:
            return ToolResult(success=True, output=f"No definition found at {path.name}:{line + 1}:{character + 1}", metadata={"definitions": [], "server": client.name})

        lines = [f"Found {len(definitions)} definition(s):"]
        for defn in definitions:
            def_file = defn.get("file", "")
            def_line = defn.get("line", 0) + 1
            def_col = defn.get("character", 0) + 1
            lines.append(f"  {def_file}:{def_line}:{def_col}")

        output = "\n".join(lines)
        return ToolResult(success=True, output=output, metadata={"definitions": definitions, "server": client.name})
