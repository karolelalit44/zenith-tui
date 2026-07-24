"""Tools module — provides all built-in tools."""

from .base import BaseTool, ToolResult
from .registry import ToolRegistry
from .permission import PermissionGate
from .bash import BashTool
from .file_read import FileReadTool
from .file_write import FileWriteTool
from .file_edit import FileEditTool
from .file_delete import FileDeleteTool
from .glob_tool import GlobTool
from .grep_tool import GrepTool
from .webfetch import WebfetchTool

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolRegistry",
    "PermissionGate",
    "BashTool",
    "FileReadTool",
    "FileWriteTool",
    "FileEditTool",
    "FileDeleteTool",
    "GlobTool",
    "GrepTool",
    "WebfetchTool",
]


def create_default_registry(timeout: int = 30) -> ToolRegistry:
    """Create a ToolRegistry with all built-in tools registered."""
    registry = ToolRegistry()
    registry.register(BashTool(timeout=timeout))
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(FileEditTool())
    registry.register(FileDeleteTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    registry.register(WebfetchTool())
    return registry
