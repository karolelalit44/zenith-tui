"""Structured output contracts for delegated specialist agents.

Every specialist mission terminates in an ``AgentResult`` regardless of
success, timeout, cancellation or provider failure. The Captain consumes
the result; the TUI renders it via the orchestration card.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AgentMetrics(BaseModel):
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    iterations: int = 0
    elapsed_ms: int = 0
    tool_calls: int = 0


class EvidenceRef(BaseModel):
    type: Literal["file_read", "grep", "glob", "list_dir", "web", "context"]
    path: str | None = None
    snippet: str = ""


class Finding(BaseModel):
    claim: str
    confidence: Literal["verified", "proposed", "unverified"] = "proposed"
    evidence_refs: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    task_id: str
    agent_id: str
    status: Literal["completed", "failed", "timed_out", "cancelled", "cached"] = "completed"
    summary: str = ""
    findings: list[Finding] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    affected_files: list[str] = Field(default_factory=list)
    proposed_changes: list[str] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    blocked: list[str] = Field(default_factory=list)
    metrics: AgentMetrics = Field(default_factory=AgentMetrics)
    error: str | None = None

    def apply_evidence_rule(self) -> None:
        """Spec §11: a verified claim must cite a path+snippet.

        Downgrades any ``verified`` Finding whose evidence_refs are empty (or
        point only at indices with no usable path/snippet) to ``proposed``.
        """
        for finding in self.findings:
            if finding.confidence != "verified":
                continue
            if not finding.evidence_refs:
                finding.confidence = "proposed"
                continue
            cited = False
            for ref in finding.evidence_refs:
                try:
                    idx = int(ref)
                except ValueError:
                    continue
                if 0 <= idx < len(self.evidence):
                    ev = self.evidence[idx]
                    if ev.path or ev.snippet:
                        cited = True
                        break
            if not cited:
                finding.confidence = "proposed"
