"""Captain -> Specialist delegation architecture (vertical slice 1).

Hierarchy: Captain owns decisions, Agents own missions, CrewMates own
focused operations, Tools own execution. This package provides the
capability-routed dispatcher surface and the first specialist, the
Codebase Scout.
"""

from .agent_definition import AgentDefinition, CodebaseScout
from .agent_result import AgentMetrics, AgentResult, EvidenceRef, Finding
from .orchestrator import (
    AGENT_TIMEOUT_SECONDS,
    DELEGATION_CACHE_TTL_SECONDS,
    MAX_CHILDREN_PER_RUN,
    MAX_DELEGATION_DEPTH,
    SCOUT_CONTEXT_BUDGET_TOKENS,
    CaptainOrchestrator,
    RepositoryIntelligenceCache,
)
from .scout import ScoutReadOnlyGuard, assemble_result, build_scout_prompt, run_scout
from .specialist_registry import (
    MIN_CAPABILITY_SCORE,
    SpecialistRegistry,
    avoid_match,
    score_prompt,
)
from .task_envelope import AgentTask, build_task_envelope, task_signature

__all__ = [
    "AGENT_TIMEOUT_SECONDS",
    "DELEGATION_CACHE_TTL_SECONDS",
    "MAX_CHILDREN_PER_RUN",
    "MAX_DELEGATION_DEPTH",
    "MIN_CAPABILITY_SCORE",
    "SCOUT_CONTEXT_BUDGET_TOKENS",
    "AgentDefinition",
    "AgentMetrics",
    "AgentResult",
    "AgentTask",
    "CaptainOrchestrator",
    "CodebaseScout",
    "EvidenceRef",
    "Finding",
    "RepositoryIntelligenceCache",
    "ScoutReadOnlyGuard",
    "SpecialistRegistry",
    "assemble_result",
    "avoid_match",
    "build_scout_prompt",
    "build_task_envelope",
    "run_scout",
    "score_prompt",
    "task_signature",
]
