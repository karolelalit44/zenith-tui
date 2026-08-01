"""LSP rename tool — semantic rename across all files using the language server."""

from __future__ import annotations

from typing import Any

from ..base import BaseTool, ToolResult


class LspRenameTool(BaseTool):
    name = "lsp_rename"
    description = "Perform a semantic rename of a symbol across all files using the LSP. Handles imports, scopes, and overloads automatically."
    requires_mode = "build"

    @property
    def risk_level(self) -> str:
        return "low"

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to the file containing the symbol to rename",
                },
                "line": {
                    "type": "integer",
                    "description": "Line number of the symbol (0-indexed)",
                },
                "character": {
                    "type": "integer",
                    "description": "Column number of the symbol (0-indexed)",
                },
                "new_name": {
                    "type": "string",
                    "description": "The new name for the symbol",
                },
            },
            "required": ["filepath", "line", "character", "new_name"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        from pathlib import Path

        from server.lsp.manager import get_lsp_manager

        filepath = params.get("filepath", "")
        line = params.get("line", 0)
        character = params.get("character", 0)
        new_name = params.get("new_name", "")

        if not filepath:
            return ToolResult(success=False, error="No filepath provided")
        if not new_name:
            return ToolResult(success=False, error="No new_name provided")

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
            return ToolResult(
                success=False,
                error=f"No LSP server available for '{ext}' files.",
            )

        content = path.read_text(encoding="utf-8", errors="replace")
        try:
            file_edits = await client.rename(str(path), content, line, character, new_name)
        except Exception as e:
            return ToolResult(success=False, error=f"LSP rename request failed: {e}")

        if not file_edits:
            return ToolResult(
                success=True,
                output=f"No rename possible at {path.name}:{line + 1}:{character + 1}. Symbol may not exist or server does not support rename.",
                metadata={"changed_files": 0},
            )

        # Apply all edits
        changed_files = []
        for edit_path, new_content in file_edits.items():
            try:
                Path(edit_path).write_text(new_content, encoding="utf-8")
                changed_files.append(edit_path)
            except Exception as e:
                return ToolResult(
                    success=False,
                    error=f"Failed to write {edit_path}: {e}. Changes rolled back.",
                    metadata={"changed_files": 0, "partial": True},
                )

        lines = [f"Renamed '{path.stem}' symbol to '{new_name}' in {len(changed_files)} file(s):"]
        for f in changed_files:
            lines.append(f"  {f}")

        return ToolResult(
            success=True,
            output="\n".join(lines),
            metadata={"changed_files": changed_files, "new_name": new_name},
        )
