"""MCP module — Model Context Protocol client for external tool servers."""

from .client import McpClient
from .manager import McpManager

__all__ = ["McpClient", "McpManager"]
