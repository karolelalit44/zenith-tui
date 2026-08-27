"""QA-10: token telemetry honesty.

usage.jsonl rows must distinguish composed-context OCCUPANCY from the
provider-billed run usage (total_tokens/prompt/completion).
"""

import pytest

from server.domain.events import Event, EventKind
from server.domain.session import Session


@pytest.fixture
async def session_id(session_repo):
    session = Session(title="Token Usage")
    await session_repo.create(session)
    return session.id


@pytest.mark.asyncio
async def test_record_distinguishes_occupancy_from_billed(usage_repo, session_id):
    await usage_repo.record(
        session_id=session_id,
        provider="acme",
        model="model-x",
        total_tokens=1500,
        context_window=16000,
        prompt_tokens=1000,
        completion_tokens=500,
        context_occupancy=1200,
    )
    rows = await usage_repo.get_per_step_stats(session_id) + _final_rows(usage_repo, session_id)
    row = rows[0]
    assert row["total_tokens"] == 1500  # provider-billed run usage
    assert row["context_occupancy"] == 1200  # composed-context occupancy
    assert row["prompt_tokens"] == 1000
    assert row["completion_tokens"] == 500
    # percent is occupancy-vs-window (not billed spend).
    assert row["percent"] == pytest.approx(1200 / 16000 * 100, abs=0.001)


def _final_rows(repo, session_id):
    from server.storage.session_file import iter_records

    return [
        r
        for r in iter_records(repo.home, session_id)
        if r.get("t") == "usage" and r.get("step_index") == -1
    ]


@pytest.mark.asyncio
async def test_record_legacy_occupancy_defaults_zero_and_percent_falls_back(usage_repo, session_id):
    await usage_repo.record(
        session_id=session_id,
        provider="acme",
        model="model-x",
        total_tokens=800,
        context_window=16000,
        prompt_tokens=500,
        completion_tokens=300,
    )
    row = _final_rows(usage_repo, session_id)[0]
    # Legacy rows: occupancy unknown (0); percent falls back to billed total.
    assert row["context_occupancy"] == 0
    assert row["total_tokens"] == 800
    assert row["percent"] == pytest.approx(800 / 16000 * 100, abs=0.001)


@pytest.mark.asyncio
async def test_get_per_step_rows_carry_occupancy_only_on_final_step(usage_repo, session_id):
    # Mirrors prompt_executor: per-step split of billed total; only the final
    # step of a turn carries the composed occupancy snapshot.
    for step in (1, 2, 3):
        await usage_repo.record(
            session_id=session_id,
            provider="acme",
            model="model-x",
            total_tokens=300,
            context_window=16000,
            prompt_tokens=200,
            completion_tokens=100,
            step_index=step,
            context_occupancy=900 if step == 3 else 0,
        )
    steps = await usage_repo.get_per_step_stats(session_id)
    assert [r["step_index"] for r in steps] == [1, 2, 3]
    assert [r["total_tokens"] for r in steps] == [300, 300, 300]
    assert [r["context_occupancy"] for r in steps] == [0, 0, 900]


@pytest.mark.asyncio
async def test_get_efficiency_final_context_uses_occupancy(usage_repo, session_id):
    await usage_repo.record(
        session_id=session_id,
        provider="acme",
        model="model-x",
        total_tokens=3000,
        context_window=16000,
        prompt_tokens=2000,
        completion_tokens=1000,
        context_occupancy=2400,
    )
    eff = await usage_repo.get_efficiency(session_id)
    assert eff["total_tokens_consumed"] == 3000
    assert eff["final_context_used"] == 2400
    assert eff["average_context_utilization"] == pytest.approx(2400 / 3000, abs=0.001)


@pytest.mark.asyncio
async def test_get_efficiency_legacy_row_falls_back_to_billed(usage_repo, session_id):
    await usage_repo.record(
        session_id=session_id,
        provider="acme",
        model="model-x",
        total_tokens=3000,
        context_window=16000,
        prompt_tokens=2000,
        completion_tokens=1000,
    )
    eff = await usage_repo.get_efficiency(session_id)
    assert eff["final_context_used"] == 3000
    assert eff["average_context_utilization"] == pytest.approx(1.0, abs=0.001)


class _Provider:
    name = "acme"
    model = "model-x"
    temperature = None
    max_tokens = None

    def _reset_cumulative_usage(self):
        pass


class _Registry:
    pass


class _SkillLoader:
    def get_skill_prompt(self):
        return ""


class _NoopScheduler:
    def schedule(self, session_id):
        pass


def _make_executor(config, s_repo, m_repo):
    from server.agents.prompt_executor import PromptExecutor

    executor = PromptExecutor(config, _Provider(), _Registry(), s_repo, m_repo, _SkillLoader())
    # The real scheduler spawns a background summarizer task that outlives the
    # test event loop; stub it out for the recording-path assertion.
    executor._summary_scheduler = _NoopScheduler()
    return executor


@pytest.mark.asyncio
async def test_execute_persists_billed_and_occupancy_separately(
    config, session_repo, message_repo, monkeypatch
):
    from server.agents.prompt_executor import PromptExecutor, RecoverableAgentLoop
    from server.storage.usage_store import FileTokenUsageRepository

    session = Session(title="t")
    await session_repo.create(session)

    executor = PromptExecutor(
        config, _Provider(), _Registry(), session_repo, message_repo, _SkillLoader()
    )
    executor._summary_scheduler = _NoopScheduler()

    async def fake_process_prompt(self, content, session_id, history, mode, **kwargs):
        yield Event(
            kind=EventKind.SUCCESS,
            session_id=session_id,
            data={
                "message": "done",
                "tokenInfo": {
                    "used": 1200,  # composed-context occupancy
                    "runTotal": 1500,  # provider-billed run usage
                    "runPrompt": 1000,
                    "runCompletion": 500,
                    "total": 16000,
                },
            },
        )

    monkeypatch.setattr(RecoverableAgentLoop, "process_prompt", fake_process_prompt)
    await executor._execute(session.id, "do it", "build", None, None)

    usage_repo = FileTokenUsageRepository(session_repo.home)
    row = _final_rows(usage_repo, session.id)[0]
    # The QA-10 defect: `used` (occupancy) must NOT overwrite the billed total.
    assert row["total_tokens"] == 1500
    assert row["context_occupancy"] == 1200
    assert row["prompt_tokens"] == 1000
    assert row["completion_tokens"] == 500
    assert row["percent"] == pytest.approx(1200 / 16000 * 100, abs=0.001)
