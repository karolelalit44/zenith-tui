"""Module 07 additive interface-lock: simple busy/idle session status.

The over-engineered SessionState machine and session_workspace file-tracking
are Phase-3 removals; this covers the additive RunStatus contract that the
storage layer (module 21) and consumers will persist/resume from.
"""

import pytest

from server.domain.session import RunStatus, Session
from server.domain.domain import SessionState


class TestRunStatus:
    def test_enum_values(self):
        assert RunStatus.IDLE.value == "idle"
        assert RunStatus.BUSY.value == "busy"

    def test_default_is_idle(self):
        assert Session().run_status is RunStatus.IDLE

    def test_mark_busy_then_idle(self):
        s = Session()
        s.mark_busy()
        assert s.run_status is RunStatus.BUSY
        assert s.status == "busy"
        s.mark_idle()
        assert s.run_status is RunStatus.IDLE
        assert s.status == "idle"

    def test_status_round_trips_through_pydantic_dump(self):
        s = Session()
        s.mark_busy()
        dumped = s.model_dump()
        assert dumped["run_status"] == RunStatus.BUSY
        reloaded = Session(**dumped)
        assert reloaded.run_status is RunStatus.BUSY

    def test_mark_busy_updates_updated_at(self):
        s = Session()
        before = s.updated_at
        s.mark_busy()
        assert s.updated_at >= before

    def test_mark_idle_updates_updated_at(self):
        s = Session()
        s.mark_busy()
        busy_ts = s.updated_at
        s.mark_idle()
        assert s.updated_at >= busy_ts

    def test_status_property_string(self):
        assert Session().status == "idle"
        s = Session()
        s.mark_busy()
        assert s.status == "busy"


class TestSessionStateMachineEdges:
    def test_archived_is_terminal(self):
        s = Session()
        s.transition(SessionState.ARCHIVED)
        with pytest.raises(ValueError):
            s.transition(SessionState.ACTIVE)

    def test_active_self_transition(self):
        s = Session()
        s.transition(SessionState.ACTIVE)
        s.transition(SessionState.ACTIVE)
        assert s.state is SessionState.ACTIVE

    def test_archive_sets_inactive(self):
        s = Session()
        s.transition(SessionState.ACTIVE)
        s.archive()
        assert s.state is SessionState.ARCHIVED
        assert s.is_active is False


class TestSessionHelpers:
    def test_update_context(self):
        s = Session()
        s.update_context(500, 1000)
        assert s.context_used == 500
        assert s.context_window == 1000
        assert s.context_percent == 50.0

    def test_update_context_zero_window(self):
        s = Session()
        s.update_context(5, 0)
        assert s.context_percent == 0.0

    def test_add_tokens(self):
        s = Session()
        s.add_tokens(100, cost=0.5)
        s.add_tokens(50, cost=0.25)
        assert s.total_tokens == 150
        assert s.total_cost == 0.75

    def test_add_child_dedupes(self):
        s = Session()
        s.add_child("c1")
        s.add_child("c1")
        assert s.child_session_ids == ["c1"]

    def test_to_summary_dict(self):
        s = Session(title="T")
        d = s.to_summary_dict()
        assert d["title"] == "T"
        assert d["state"] == SessionState.CREATED.value
        assert "created_at" in d
