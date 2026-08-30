"""Unit tests for the delegation data contracts (spec §Data contracts)."""

import pytest
from pydantic import ValidationError

from server.agents.delegation import (
    AgentDefinition,
    AgentResult,
    AgentTask,
    ApogeeCrewmate,
    EvidenceRef,
    Finding,
    build_task_envelope,
    task_signature,
)


class TestAgentResultDefaults:
    def test_result_defaults_are_safe(self):
        result = AgentResult(task_id="t-1", agent_id="apogee")
        assert result.status == "completed"
        assert result.summary == ""
        assert result.findings == []
        assert result.evidence == []
        assert result.affected_files == []
        assert result.proposed_changes == []
        assert result.unverified == []
        assert result.blocked == []
        assert result.metrics.tokens_used == 0
        assert result.error is None

    def test_status_enum_rejects_invalid(self):
        with pytest.raises(ValidationError):
            AgentResult(task_id="t", agent_id="a", status="exploded")

    def test_metrics_default_independent_per_instance(self):
        a = AgentResult(task_id="t1", agent_id="a")
        b = AgentResult(task_id="t2", agent_id="a")
        a.metrics.tokens_used = 500
        assert b.metrics.tokens_used == 0


class TestFinding:
    def test_confidence_enum_accepts_known_values(self):
        for confidence in ("verified", "proposed", "unverified"):
            Finding(claim="c", confidence=confidence)

    def test_confidence_enum_rejects_invalid(self):
        with pytest.raises(ValidationError):
            Finding(claim="c", confidence="absolutely-certain")

    def test_evidence_refs_default_empty(self):
        finding = Finding(claim="c")
        assert finding.evidence_refs == []


class TestEvidenceRef:
    def test_path_optional(self):
        ref = EvidenceRef(type="context", snippet="from memory")
        assert ref.path is None
        assert ref.snippet == "from memory"

    def test_type_rejects_unknown(self):
        with pytest.raises(ValidationError):
            EvidenceRef(type="mind_read")


class TestEvidenceRule:
    def test_verified_without_refs_downgraded_to_proposed(self):
        result = AgentResult(
            task_id="t",
            agent_id="a",
            findings=[Finding(claim="X exists", confidence="verified")],
        )
        result.apply_evidence_rule()
        assert result.findings[0].confidence == "proposed"

    def test_verified_with_path_and_snippet_citation_stays_verified(self):
        result = AgentResult(
            task_id="t",
            agent_id="a",
            findings=[Finding(claim="X exists", confidence="verified", evidence_refs=["0"])],
            evidence=[
                EvidenceRef(
                    type="file_read", path="server/domain/session.py", snippet="class Session"
                )
            ],
        )
        result.apply_evidence_rule()
        assert result.findings[0].confidence == "verified"

    def test_verified_with_dangling_index_downgraded(self):
        result = AgentResult(
            task_id="t",
            agent_id="a",
            findings=[Finding(claim="X", confidence="verified", evidence_refs=["9"])],
        )
        result.apply_evidence_rule()
        assert result.findings[0].confidence == "proposed"

    def test_proposed_untouched(self):
        result = AgentResult(
            task_id="t",
            agent_id="a",
            findings=[Finding(claim="maybe", confidence="proposed")],
        )
        result.apply_evidence_rule()
        assert result.findings[0].confidence == "proposed"


class TestAgentTask:
    def test_envelope_fields_from_definition(self):
        task = build_task_envelope(
            objective="Investigate sessions",
            definition=ApogeeCrewmate,
            session_id="s-1",
            max_context_tokens=64_000,
        )
        assert isinstance(task, AgentTask)
        assert task.agent_id == ApogeeCrewmate.id
        assert task.capability == ApogeeCrewmate.capabilities[0]
        assert task.depth == 0
        assert task.child_session_id is None
        assert task.task_id

    def test_crewmate_definition_is_not_a_delegator(self):
        crewmate: AgentDefinition = ApogeeCrewmate
        assert crewmate.can_delegate is False
        assert crewmate.max_crewmates == 0
        assert crewmate.allowed_crewmates == []
        assert crewmate.delegation_depth == 0
        assert set(crewmate.allowed_tools) == {"file_read", "glob", "grep", "list_dir"}
        assert crewmate.allowed_mcp == {}


class TestTaskSignature:
    def test_deterministic(self):
        s1 = task_signature("investigate sessions", "apogee", "s1")
        s2 = task_signature("investigate sessions", "apogee", "s1")
        assert s1 == s2

    def test_normalizes_case_and_whitespace(self):
        s1 = task_signature("  Investigate   SESSIONS  ", "apogee", "s1")
        s2 = task_signature("investigate sessions", "apogee", "s1")
        assert s1 == s2

    def test_differs_across_agent_or_session(self):
        base = task_signature("obj", "apogee", "s1")
        assert base != task_signature("obj", "other-agent", "s1")
        assert base != task_signature("obj", "apogee", "s2")

    def test_differs_across_objectives(self):
        assert task_signature("obj A", "a", "s") != task_signature("obj B", "a", "s")
