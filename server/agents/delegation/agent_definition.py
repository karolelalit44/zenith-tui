"""Agent capability contracts.

An ``AgentDefinition`` describes what a specialist may do, which tools it
may use and whether it may itself delegate. The Captain routes by
capability; the definition is the contract the specialist is held to.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from server.config.constants import READ_ONLY_TOOLS

SCOUT_MODE = "scout"

AGENT_RESULT_SCHEMA: dict = {
    "type": "object",
    "required": ["task_id", "agent_id", "status", "summary"],
    "properties": {
        "task_id": {"type": "string"},
        "agent_id": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["completed", "failed", "timed_out", "cancelled", "cached"],
        },
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["verified", "proposed", "unverified"],
                    },
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["claim"],
            },
        },
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["file_read", "grep", "glob", "list_dir", "web", "context"],
                    },
                    "path": {"type": ["string", "null"]},
                    "snippet": {"type": "string"},
                },
            },
        },
        "affected_files": {"type": "array", "items": {"type": "string"}},
        "proposed_changes": {"type": "array", "items": {"type": "string"}},
        "unverified": {"type": "array", "items": {"type": "string"}},
        "blocked": {"type": "array", "items": {"type": "string"}},
    },
}


class AgentDefinition(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    name: str
    role: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    best_for: list[str] = Field(default_factory=list)
    avoid_for: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_mcp: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=lambda: AGENT_RESULT_SCHEMA)
    can_delegate: bool = False
    max_crewmates: int = 0
    allowed_crewmates: list[str] = Field(default_factory=list)
    delegation_depth: int = 0
    model_override: str | None = None


CodebaseScout = AgentDefinition(
    id="codebase-scout",
    name="Codebase Scout",
    role="Codebase Investigator",
    description=(
        "Read-only codebase investigator: traces how a feature works, where "
        "state lives, and what a change would touch, returning evidence-backed "
        "findings."
    ),
    capabilities=[
        "codebase_investigation",
        "persistence_analysis",
        "context_trace",
    ],
    best_for=[
        "how does X work",
        "where is X stored",
        "what would change",
        "investigate",
        "trace",
        "migration impact",
        "persisted",
    ],
    avoid_for=[
        "write",
        "create a file",
        "fix",
        "refactor",
        "migrate now",
        "run the app",
        "add a test",
    ],
    allowed_tools=READ_ONLY_TOOLS,
    allowed_mcp={},
    can_delegate=False,
    max_crewmates=0,
    allowed_crewmates=[],
    delegation_depth=0,
)
