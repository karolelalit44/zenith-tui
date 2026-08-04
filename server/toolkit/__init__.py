
from .base import BaseTool, ToolContext, ToolMiddleware, ToolResult
from .registry import ToolRegistry
from .tools.agent_tool import SubAgentTool
from .tools.bash import BashTool
from .tools.file_delete import FileDeleteTool
from .tools.file_edit import FileEditTool
from .tools.file_read import FileReadTool
from .tools.file_write import FileWriteTool
from .tools.glob import GlobTool
from .tools.grep import GrepTool
from .tools.job_kill import JobKillTool
from .tools.job_output import JobOutputTool
from .tools.lsp_definition import LspDefinitionTool
from .tools.lsp_diagnostics import LspDiagnosticsTool
from .tools.lsp_rename import LspRenameTool
from .tools.mcp_tool import McpToolWrapper
from .tools.multi_edit import MultiEditTool
from .tools.question import QuestionTool
from .tools.todo import TodoTool
from .tools.webfetch import WebfetchTool

__all__ = ["BaseTool", "BashTool", "FileDeleteTool", "FileEditTool", "FileReadTool", "FileWriteTool", "GlobTool", "GrepTool", "JobKillTool", "JobOutputTool", "LspDefinitionTool", "LspDiagnosticsTool", "LspRenameTool", "McpToolWrapper", "MultiEditTool", "QuestionTool", "SubAgentTool", "TodoTool", "ToolContext", "ToolMiddleware", "ToolRegistry", "ToolResult", "WebfetchTool"]


def create_default_registry(timeout: int = 30, provider: object | None = None, permission_service: object | None = None, hooks: object | None = None) -> ToolRegistry:
    from .middleware import HookMiddleware, PermissionMiddleware, SafetyCheckMiddleware

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
    if hooks is not None:
        from server.domain.hooks import HookRunner

        registry.register_middleware(HookMiddleware(HookRunner(hooks)))
    registry.register_middleware(SafetyCheckMiddleware())
    if permission_service is not None:
        registry.register_middleware(PermissionMiddleware(service=permission_service))
    return registry
