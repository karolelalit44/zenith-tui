"""QA-3: evidence-aware finalization.

The execution manifest (created/modified/verified) is authoritative. When the
model's prose claims work — ``Created X``, ``Fixed the bug``, ``Done`` — but
the manifest proves none of it happened (no created/modified files), the
persisted assistant message must be rewritten to a factual correction instead
of letting prose contradict the manifest. The persisted final text is also
capped so tool/reasoning noise cannot become the canonical message.
"""

from __future__ import annotations

import pytest

from server.agents.prompt_executor import (
    _build_crafted_handoff,
    _claim_contradicts_evidence,
    _rewrite_false_completion_claim,
)
from server.domain.events import Event, EventKind


def _manifest(**overrides) -> dict:
    payload = {
        "created": [],
        "modified": [],
        "remaining": [],
        "completed": False,
        "stalled": False,
        "verified": False,
        "checks": [],
    }
    payload.update(overrides)
    return payload


def _no_work_manifest() -> dict:
    return _manifest(created=[], modified=[], verified=False)


class TestClaimClassification:
    def test_created_file_claim_isolated(self):
        assert _claim_contradicts_evidence("Created the file api.py.") is True

    def test_wrote_file_claim(self):
        assert _claim_contradicts_evidence("I wrote output/config.json for you.") is True

    def test_done_claim(self):
        assert _claim_contradicts_evidence("Done — implementation complete.") is True

    def test_fixed_claim(self):
        assert _claim_contradicts_evidence("Fixed the failing test.") is True

    def test_explicit_negative_not_corrected(self):
        assert _claim_contradicts_evidence("Could not create the file.") is False
        assert _claim_contradicts_evidence("I was unable to write the file.") is False
        assert _claim_contradicts_evidence("The build failed, nothing new was created.") is False

    def test_plain_answer_uncorrected(self):
        assert _claim_contradicts_evidence("The answer is 42.") is False
        assert _claim_contradicts_evidence("") is False
        assert _claim_contradicts_evidence("   ") is False

    def test_present_tense_only_naming_not_enough(self):
        assert _claim_contradicts_evidence("Here is the current file.") is False


class TestRewrite:
    def test_false_claim_prefixes_not_implemented(self):
        rewritten = _rewrite_false_completion_claim(
            "Created api.py and it should work now.", _no_work_manifest()
        )
        assert rewritten.startswith("[Not implemented] Created api.py")

    def test_true_manifest_keeps_prose(self):
        m = _manifest(created=["api.py"], verified=True, completed=True)
        text = "Created api.py and verified it."
        assert _rewrite_false_completion_claim(text, m) == text

    def test_negative_prose_kept(self):
        text = "I could not create the file because the path was blocked."
        assert _rewrite_false_completion_claim(text, _no_work_manifest()) == text

    def test_idempotent(self):
        text = "Created api.py."
        first = _rewrite_false_completion_claim(text, _no_work_manifest())
        second = _rewrite_false_completion_claim(first, _no_work_manifest())
        assert second == first


class TestContradictionFlowsThroughHandoff:
    """The contradiction correction reaches the persisted message body."""

    def test_false_claim_is_corrected_in_handoff_body(self):
        m = _no_work_manifest()
        handoff = _build_crafted_handoff(m, "Created api.py, everything works now.")
        assert "[Not implemented]" in handoff
        assert "(No file was created or modified in this turn.)" in handoff

    def test_empty_manifest_with_plain_answer_kept(self):
        handoff = _build_crafted_handoff(_no_work_manifest(), "No changes needed.")
        assert "[Not implemented]" not in handoff
        assert "No changes needed." in handoff

    def test_worked_manifest_never_not_implemented(self):
        m = _manifest(created=["a.py"], verified=True, completed=True)
        handoff = _build_crafted_handoff(m, "Created a.py and verified.")
        assert "[Not implemented]" not in handoff
        assert "Created: a.py" in handoff


class _FakeMessageRepo:
    def __init__(self) -> None:
        self.created: list = []

    async def create(self, message) -> None:
        self.created.append(message)


class _Stub:
    def __init__(self, repo, config):
        self._message_repo = repo
        self._config = config
        self._provider = None


@pytest.fixture
def config():
    from server.config.settings import AppSettings

    return AppSettings(db_path="/tmp/evidence_finalization_test.db", workspace_root="/tmp")


class TestPersistAssistantMessage:
    async def _persist(self, stub, response_text, events):
        import types

        from server.agents.prompt_executor import PromptExecutor

        stub._summarize_handoff = types.MethodType(PromptExecutor._summarize_handoff, stub)
        await PromptExecutor._persist_assistant_message(stub, "s1", response_text, events)

    def _manifest_event(self, manifest: dict) -> Event:
        return Event(kind=EventKind.TURN_MANIFEST, data={"manifest": manifest})

    async def test_false_claim_persisted_as_not_implemented(self, config):
        repo = _FakeMessageRepo()
        stub = _Stub(repo, config)
        events = [self._manifest_event(_no_work_manifest())]
        await self._persist(stub, "Created api.py, it now serves requests.", events)
        assert len(repo.created) == 1
        content = repo.created[0].content
        assert "[Not implemented]" in content
        assert "(No file was created or modified in this turn.)" in content

    async def test_honest_no_work_prose_kept(self, config):
        repo = _FakeMessageRepo()
        stub = _Stub(repo, config)
        events = [self._manifest_event(_no_work_manifest())]
        await self._persist(stub, "The file does not exist, I could not modify it.", events)
        assert len(repo.created) == 1
        assert "[Not implemented]" not in repo.created[0].content
        assert "could not modify it" in repo.created[0].content

    async def test_worked_claim_never_corrected(self, config):
        repo = _FakeMessageRepo()
        stub = _Stub(repo, config)
        m = _manifest(created=["a.py"], modified=["b.py"], verified=True, completed=True)
        events = [self._manifest_event(m)]
        await self._persist(stub, "Created a.py and fixed b.py.", events)
        assert len(repo.created) == 1
        content = repo.created[0].content
        assert "[Not implemented]" not in content
        assert "Created: a.py" in content
        assert "Modified: b.py" in content

    async def test_persisted_message_capped(self, config):
        repo = _FakeMessageRepo()
        stub = _Stub(repo, config)
        m = _manifest(created=["big.py"], verified=True, completed=True)
        huge = "Detail. " * 5000  # far beyond _HANDOFF_MAX_CHARS
        events = [
            self._manifest_event(m),
            Event(kind=EventKind.MESSAGE, data={"text": huge}),
        ]
        await self._persist(stub, huge, events)
        assert len(repo.created) == 1
        content = repo.created[0].content
        from server.agents.prompt_executor import _HANDOFF_MAX_CHARS

        assert len(content) <= _HANDOFF_MAX_CHARS + 1  # + ellipsis
        assert "[Not implemented]" not in content


class TestPlanArtifactContract:
    """QA-6.5: plan mode — an unattempted plan.md/todo.md cannot be claimed."""

    def _plan_manifest(self, missing: list[str] | None = None) -> dict:
        missing = missing if missing is not None else ["plan.md", "todo.md"]
        return _manifest(
            completed=False,
            plan_artifacts={
                "plan_written": "plan.md" not in missing,
                "todo_written": "todo.md" not in missing,
                "missing": missing,
            },
        )

    def test_handoff_surfaces_missing_plan_artifact(self):
        m = self._plan_manifest(missing=["plan.md"])
        handoff = _build_crafted_handoff(m, "Here is the full plan.")
        assert "Plan artifacts not written: plan.md" in handoff

    def test_handoff_mentions_todo_when_missing(self):
        m = self._plan_manifest(missing=["todo.md"])
        handoff = _build_crafted_handoff(m, "Plan complete.")
        assert "Plan artifacts not written: todo.md" in handoff

    def test_rewrite_names_missing_plan_artifact(self):
        m = self._plan_manifest(missing=["plan.md"])
        corrected = _rewrite_false_completion_claim("Created the plan file.", m)
        assert "[Not implemented]" in corrected
        assert "Plan artifacts not written: plan.md" in corrected

    def test_rewrite_keeps_honest_plan_prose(self):
        m = self._plan_manifest(missing=["plan.md"])
        text = "I could not write plan.md."
        assert _rewrite_false_completion_claim(text, m) == text

    def test_plan_manifest_with_artifacts_has_no_remaining(self):
        m = self._plan_manifest(missing=[])
        assert m["plan_artifacts"]["plan_written"] is True
        assert m["plan_artifacts"]["todo_written"] is True

    async def test_persisted_plan_claim_corrected(self, config):
        repo = _FakeMessageRepo()
        stub = _Stub(repo, config)
        m = self._plan_manifest(missing=["plan.md"])
        events = [Event(kind=EventKind.TURN_MANIFEST, data={"manifest": m})]

        import types

        from server.agents.prompt_executor import PromptExecutor

        stub._summarize_handoff = types.MethodType(PromptExecutor._summarize_handoff, stub)
        await PromptExecutor._persist_assistant_message(
            stub, "s1", "I have written the complete plan to plan.md.", events
        )
        assert len(repo.created) == 1
        content = repo.created[0].content
        assert "[Not implemented]" in content
        assert "Plan artifacts not written: plan.md" in content
