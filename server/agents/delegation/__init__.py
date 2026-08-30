"""Captain -> Specialist delegation architecture (vertical slice 1).

Hierarchy: Captain owns decisions, Crewmates own missions and focused
operations, Tools own execution. This package provides the
capability-routed dispatcher surface and the first specialist, the
Apogee Crewmate.
"""

from .agent_definition import AgentDefinition, ApogeeCrewmate
from .agent_result import AgentMetrics, AgentResult, EvidenceRef, Finding
from .orchestrator import (
    AGENT_TIMEOUT_SECONDS,
    DELEGATION_CACHE_TTL_SECONDS,
    MAX_CHILDREN_PER_RUN,
    MAX_DELEGATION_DEPTH,
    CREWMATE_CONTEXT_BUDGET_TOKENS,
    CaptainOrchestrator,
    RepositoryIntelligenceCache,
)
from .scout import CrewmateReadOnlyGuard, assemble_result, build_crewmate_prompt, run_crewmate
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
    "CREWMATE_CONTEXT_BUDGET_TOKENS",
    "AgentDefinition",
    "AgentMetrics",
    "AgentResult",
    "AgentTask",
    "CaptainOrchestrator",
    "ApogeeCrewmate",
    "EvidenceRef",
    "Finding",
    "RepositoryIntelligenceCache",
    "CrewmateReadOnlyGuard",
    "SpecialistRegistry",
    "assemble_result",
    "avoid_match",
    "build_crewmate_prompt",
    "build_task_envelope",
    "run_crewmate",
    "score_prompt",
    "task_signature",
]
