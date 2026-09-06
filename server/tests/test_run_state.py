"""QA-4: structured SessionRunState.

The run state is the authoritative, evidence-derived record of a session's run.
It is built from *executed* tool events and turn manifests — never from model
prose. Tests cover the state machine, persistence round-trip, bounded history,
safe hydration of old/malformed records, and that the loop/prompt-executor
wiring persists it into ``session.metadata["run_state"]``.
"""

from __future__ import annotations

import pytest

from server.agents.run_state import (
    _MAX_FINDINGS,
    RUN_STATUSES,
    SessionRunState,
    from_dict,
    merge_run_state,
    new_run_state,
    update_from_event,
)
from server.domain.events import Event, EventKind


def _ev(kind: EventKind, data: dict | None = None, ts: float = 1.0) -> Event:
    return Event(kind=kind, data=data or {}, timestamp=ts)


class TestNewAndMerge:
    def test_new_run_state_defaults(self):
        s = new_run_state(objective="Fix bug", mode="build", ts=5.0)
        assert s.objective == "Fix bug"
        assert s.mode == "build"
        assert s.status == "idle"
        assert s.started_at == 5.0
        assert s.tool_history == []
        assert s.manifest is None
        assert s.final is None

    def test_merge_carries_todo_and_plan_but_not_history(self):
        prev = SessionRunState(
            objective="Old",
            mode="plan",
            status="completed",
            todo=[{"id": "t1", "title": "a"}],
            plan="plan text",
            tool_history=[{"kind": "tool_call", "tool": "file_read"}],
        )
        merged = merge_run_state(prev, ts=9.0)
        assert merged.todo == prev.todo
        assert merged.plan == "plan text"
        assert merged.tool_history == []
        assert merged.status == "idle"
        assert merged.manifest is None
        assert merged.started_at == 9.0

    def test_merge_without_previous_returns_fresh(self):
        merged = merge_run_state(None, ts=1.0)
        assert isinstance(merged, SessionRunState)
        assert merged.status == "idle"


class TestStatusMachine:
    def test_tool_call_transitions_to_executing(self):
        s = new_run_state()
        update_from_event(s, EventKind.TOOL_CALL, {"tool": "file_read"}, 1.0)
        assert s.status == "executing"
        assert s.tool_history
        assert s.tool_history[0]["tool"] == "file_read"
        assert s.progress

    def test_success_tool_result_transitions_to_verifying(self):
        s = new_run_state()
        update_from_event(s, EventKind.TOOL_CALL, {"tool": "bash"}, 1.0)
        update_from_event(s, EventKind.TOOL_RESULT, {"tool": "bash", "success": True}, 2.0)
        assert s.status == "verifying"
        assert s.tool_history[-1]["status"] == "success"

    def test_failed_tool_result_marks_blocked(self):
        s = new_run_state()
        update_from_event(s, EventKind.TOOL_CALL, {"tool": "bash"}, 1.0)
        update_from_event(s, EventKind.TOOL_RESULT, {"tool": "bash", "success": False}, 2.0)
        assert s.status == "blocked"

    def test_turn_manifest_with_work_finalizing(self):
        s = new_run_state()
        manifest = {"created": ["a.py"], "modified": [], "completed": True}
        update_from_event(s, EventKind.TURN_MANIFEST, {"manifest": manifest}, 3.0)
        assert s.manifest == manifest
        assert s.status == "finalizing"

    def test_success_closes_run(self):
        s = new_run_state()
        update_from_event(s, EventKind.SUCCESS, {"message": "done"}, 4.0)
        assert s.status == "completed"
        assert s.final and s.final["kind"] == "success"

    def test_error_marks_failed(self):
        s = new_run_state()
        update_from_event(s, EventKind.ERROR, {"message": "boom", "code": "X"}, 4.0)
        assert s.status == "failed"
        assert s.final and s.final["code"] == "X"

    def test_warning_does_not_change_status(self):
        s = new_run_state()
        update_from_event(s, EventKind.TOOL_CALL, {"tool": "file_read"}, 1.0)
        update_from_event(s, EventKind.WARNING, {"message": "watch"}, 2.0)
        assert s.status == "executing"

    def test_error_records_failure_finding(self):
        s = new_run_state()
        update_from_event(s, EventKind.ERROR, {"message": "boom", "code": "X"}, 4.0)
        assert any("Run failed: boom" in f for f in s.findings)

    def test_manifest_verification_evidence_populates_findings(self):
        s = new_run_state()
        manifest = {
            "created": ["a.py"],
            "modified": [],
            "completed": False,
            "checks": [
                {"tool": "bash", "output_len": 120, "seq": 1},
                {"tool": "bash", "output_len": 0, "seq": 2},
                "not-a-dict",
            ],
        }
        update_from_event(s, EventKind.TURN_MANIFEST, {"manifest": manifest}, 3.0)
        assert s.status == "verifying"
        assert any("Verified via bash" in f for f in s.findings)
        assert len(s.findings) == 1

    def test_findings_dedup_and_bound(self):
        s = new_run_state()
        for _ in range(3):
            update_from_event(
                s,
                EventKind.TURN_MANIFEST,
                {
                    "manifest": {
                        "checks": [{"tool": "bash", "output_len": 10, "seq": 1}],
                    }
                },
                3.0,
            )
        assert len(s.findings) == 1
        for i in range(60):
            update_from_event(s, EventKind.ERROR, {"message": f"err {i}", "code": "X"}, float(i))
        assert len(s.findings) <= _MAX_FINDINGS


class TestPersistence:
    def test_round_trip(self):
        s = new_run_state(objective="O", mode="build", ts=1.0)
        update_from_event(s, EventKind.TOOL_CALL, {"tool": "file_read"}, 2.0)
        update_from_event(s, EventKind.TOOL_RESULT, {"tool": "file_read", "success": True}, 3.0)
        data = s.to_dict()
        back = from_dict(data)
        assert back.objective == "O"
        assert back.status == s.status
        assert len(back.tool_history) == len(s.tool_history)
        assert back.tool_history == s.tool_history

    def test_empty_and_malformed_hydrate_safely(self):
        assert from_dict(None).status == "idle"
        assert from_dict({}).status == "idle"
        assert from_dict({"status": "completed"}).status == "completed"
        assert from_dict("garbage").status == "idle"
        assert from_dict(None).tool_history == []

    def test_history_bounded(self):
        s = new_run_state()
        for i in range(100):
            update_from_event(s, EventKind.TOOL_CALL, {"tool": f"t{i}"}, float(i))
        data = s.to_dict()
        assert len(data["tool_history"]) <= 40

    def test_statuses_are_valid(self):
        assert "idle" in RUN_STATUSES
        assert set(RUN_STATUSES) >= {
            "investigating",
            "planning",
            "executing",
            "verifying",
            "finalizing",
            "blocked",
            "failed",
            "completed",
        }


class TestPromptExecutorPersistence:
    """The prompt-executor wiring persists run state into session metadata."""

    @pytest.mark.asyncio
    async def test_execute_persists_run_state(self):
        from server.agents.prompt_executor import PromptExecutor

        class _Repo:
            def __init__(self):
                self.session = None
                self.created_messages = []
                self.token_usage = []
                self.budget = {"active": False, "max_monthly_cost": 0}
                self.metadata = {}

            async def get(self, session_id):
                if self.session is None:
                    from server.domain.session import Session

                    self.session = Session(id=session_id)
                return self.session

            async def update(self, session):
                return session

            async def get_metadata(self, session_id):
                return dict(self.metadata)

            async def merge_metadata(self, session_id, updates):
                self.metadata.update(updates)
                return dict(self.metadata)

            async def add_tokens(self, session_id, tokens):
                return self.session

            def _new(self):
                return self.session

        class _MsgRepo:
            def __init__(self):
                self.messages = []

            async def get_by_session(self, session_id):
                return []

            async def create(self, msg):
                self.messages.append(msg)

        class _Manager:
            def __init__(self):
                self.sent = []

            async def send_event(self, session_id, event):
                self.sent.append(event)

        class _Summarizer:
            async def schedule(self, session_id):
                pass

        class _Provider:
            name = "test"
            model = "test-model"

            def _reset_cumulative_usage(self):
                pass

        class _Registry:
            pass

        repo = _Repo()
        msg_repo = _MsgRepo()
        from server.config.settings import AppSettings

        config = AppSettings(home_dir="/tmp/run_state_test.db", workspace_root="/tmp")
        executor = PromptExecutor(
            config,
            _Provider(),
            _Registry(),
            repo,
            msg_repo,
        )

        # Emulate a completed turn with tool activity + success.
        events = [
            _ev(EventKind.TOOL_CALL, {"tool": "file_read"}),
            _ev(EventKind.TOOL_RESULT, {"tool": "file_read", "success": True}),
            _ev(EventKind.SUCCESS, {"message": "done"}),
        ]
        snapshot = await PromptExecutor._persist_run_state(
            executor, "s1", "read the file", "build", events, 1.0
        )
        assert snapshot is not None
        assert snapshot["status"] == "completed"
        assert snapshot["final"]["kind"] == "success"
        # Run state is persisted through the targeted merge_metadata path.
        run_state = (repo.metadata or {}).get("run_state")
        assert run_state is not None
        assert run_state["status"] == "completed"
        assert run_state["mode"] == "build"
        assert run_state["objective"] == "read the file"
        assert len(run_state["tool_history"]) >= 2
        assert run_state["final"]["kind"] == "success"

    @pytest.mark.asyncio
    async def test_persist_renders_todo_md_artifact(self, temp_dir):
        from server.agents.prompt_executor import PromptExecutor
        from server.agents.todo_state import get_todo_state

        get_todo_state("s1").hydrate([])

        class _Repo:
            def __init__(self):
                self.session = None
                self.metadata = {}

            async def get(self, session_id):
                if self.session is None:
                    from server.domain.session import Session

                    self.session = Session(id=session_id, workspace_root=str(temp_dir))
                return self.session

            async def update(self, session):
                return session

            async def get_metadata(self, session_id):
                return dict(self.metadata)

            async def merge_metadata(self, session_id, updates):
                self.metadata.update(updates)
                return dict(self.metadata)

            async def add_tokens(self, session_id, tokens):
                return self.session

        class _MsgRepo:
            async def get_by_session(self, session_id):
                return []

        class _Provider:
            name = "test"
            model = "test-model"

            def _reset_cumulative_usage(self):
                pass

        class _Registry:
            pass

        from server.config.settings import AppSettings

        config = AppSettings(home_dir=str(temp_dir / "run_state.db"), workspace_root=str(temp_dir))
        executor = PromptExecutor(
            config,
            _Provider(),
            _Registry(),
            _Repo(),
            _MsgRepo(),
        )

        state = get_todo_state("s1")
        state.add("Write the module")
        state.add("Review the diff", priority="high", notes="two files")
        state.complete("t1")

        await PromptExecutor._persist_run_state(
            executor, "s1", "build the module", "build", [], 1.0
        )
        artifact = temp_dir / "todo.md"
        assert artifact.exists()
        text = artifact.read_text(encoding="utf-8")
        assert "- [x] Write the module" in text
        assert "- [ ] Review the diff (priority: high) — two files" in text
        # Empty board never clobbers a model-authored todo.md.
        get_todo_state("s1").hydrate([])
        (temp_dir / "todo.md").write_text("# Hand-written plan", encoding="utf-8")
        await PromptExecutor._persist_run_state(
            executor, "s1", "build the module", "build", [], 1.0
        )
        assert artifact.read_text(encoding="utf-8") == "# Hand-written plan"
        get_todo_state("s1").hydrate([])

    @pytest.mark.asyncio
    async def test_persist_without_session_is_noop(self):
        from server.agents.prompt_executor import PromptExecutor
        from server.config.settings import AppSettings

        class _EmptyRepo:
            async def get(self, session_id):
                return None

        executor = PromptExecutor(
            AppSettings(),
            None,
            None,
            _EmptyRepo(),
            None,
        )
        await PromptExecutor._persist_run_state(executor, "missing", "obj", "build", [], 1.0)
        # No exception raised for a missing session.
        assert True
