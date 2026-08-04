from __future__ import annotations

from typing import Any

from ..base import BaseTool, ToolResult


class WebfetchTool(BaseTool):
    name = "webfetch"
    description = "Fetch content from a URL"

    @property
    def risk_level(self) -> str:
        return "low"

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "format": {
                    "type": "string",
                    "enum": ["text", "markdown", "html"],
                    "default": "text",
                },
            },
            "required": ["url"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        url = params.get("url", "")
        if not url:
            return ToolResult(success=False, error="No URL provided")
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                content = response.text[:100000]
                return ToolResult(
                    success=True,
                    output=content,
                    metadata={"status": response.status_code, "url": url},
                )
        except ImportError:
            return ToolResult(
                success=False, error="httpx not installed. Run: pip install 'zenith[llm]'"
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
