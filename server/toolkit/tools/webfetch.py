from __future__ import annotations

from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    COST_CLASS_MEDIUM,
    LATENCY_CLASS_HIGH,
    PERMISSION_NETWORK,
    RISK_LOW,
    TOOL_DOMAIN_WEB_MCP,
)

from ..base import BaseTool, ToolResult


class WebfetchTool(BaseTool):
    name = "webfetch"
    description = "Fetch content from a URL"
    capability_id = "web_fetch"
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_NETWORK
    domains = (TOOL_DOMAIN_WEB_MCP,)
    search_terms = (
        "web",
        "fetch",
        "url",
        "http",
        "download",
        "page",
        "link",
    )
    risk_level = RISK_LOW
    cost_class = COST_CLASS_MEDIUM
    latency_class = LATENCY_CLASS_HIGH

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
