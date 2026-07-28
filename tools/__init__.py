"""Tools module — provides all built-in tools."""

from .base import BaseTool, ToolResult, ToolContext, ToolMiddleware
from .registry import ToolRegistry
from .bash import BashTool
from .file_read import FileReadTool
from .file_write import FileWriteTool
from .file_edit import FileEditTool
from .file_delete import FileDeleteTool
from .glob_tool import GlobTool
from .grep_tool import GrepTool
from .webfetch import WebfetchTool
from .job_output import JobOutputTool
from .job_kill import JobKillTool
from .multi_edit import MultiEditTool
from .question import QuestionTool
from .todo import TodoTool
from .lsp_diagnostics import LspDiagnosticsTool
from .lsp_definition import LspDefinitionTool
from .lsp_rename import LspRenameTool
from .mcp_tool import McpToolWrapper
from .agent_tool import SubAgentTool

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolContext",
    "ToolMiddleware",
    "ToolRegistry",
    "BashTool",
    "FileReadTool",
    "FileWriteTool",
    "FileEditTool",
    "FileDeleteTool",
    "GlobTool",
    "GrepTool",
    "WebfetchTool",
    "JobOutputTool",
    "JobKillTool",
    "MultiEditTool",
    "QuestionTool",
    "TodoTool",
    "LspDiagnosticsTool",
    "LspDefinitionTool",
    "LspRenameTool",
    "McpToolWrapper",
    "SubAgentTool",
]


def create_default_registry(timeout: int = 30, provider: object | None = None) -> ToolRegistry:
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
    registry.register(JobOutputTool())
    registry.register(JobKillTool())
    registry.register(MultiEditTool())
    registry.register(QuestionTool())
    registry.register(TodoTool())
    registry.register(LspDiagnosticsTool())
    registry.register(LspDefinitionTool())
    registry.register(LspRenameTool())
    agent_tool = SubAgentTool(provider=provider)
    registry.register(agent_tool)
    return registry
