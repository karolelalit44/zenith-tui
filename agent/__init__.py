"""Agent module — loop, context, prompts, recovery, runtime, coordinator."""

from .loop import AgentLoop
from .prompts import build_system_prompt
from .context import ContextManager
from .recovery import RecoverableAgentLoop
from .templates import PromptTemplate, PromptBuilder
from .runtime import AgentRuntime, DefaultAgentRuntime
from .coordinator import CoordinatorService, DefaultCoordinator
from .loop_detection import LoopDetector

__all__ = [
    "AgentLoop",
    "build_system_prompt",
    "ContextManager",
    "RecoverableAgentLoop",
    "PromptTemplate",
    "PromptBuilder",
    "AgentRuntime",
    "DefaultAgentRuntime",
    "CoordinatorService",
    "DefaultCoordinator",
    "LoopDetector",
]
