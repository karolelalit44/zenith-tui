"""Summary-card truthfulness (AGENT_RELIABILITY_PLAN P2 / P8 scenarios 7-8).

Pins:
- Summarizer degradation derives the objective from the real conversation,
  never from canned boilerplate.
- Findings are per-run: a fresh run must not inherit a previous run's failure
  notes, so a successful rerun cannot surface a stale "Run failed:" line.
"""

import pytest

from server.agents.run_state import merge_run_state
from server.agents.summarizer import ConversationSummarizer
from server.config.settings import AppSettings
from server.domain.message import Message
from server.providers.base import BaseProvider


class _FailingProvider(BaseProvider):
    def __init__(self):
        super().__init__("failing", "failing-model")

    async def complete(self, messages, tools=None):
        raise RuntimeError("llm down")

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        if False:
            yield None
        raise RuntimeError("llm down")

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["failing-model"]


@pytest.fixture
def config():
    return AppSettings(home_dir="/tmp/summary_truth_test.db", workspace_root="/tmp")


@pytest.mark.asyncio
async def test_fallback_derives_objective_from_real_prompt(config):
    summarizer = ConversationSummarizer(config, _FailingProvider())
    messages = [
        Message(
            session_id="s1",
            role="user",
            content="point out all the major features of our app in brief",
        ),
        Message(session_id="s1", role="assistant", content="exploring the codebase"),
    ]
    out = await summarizer.summarize(messages, model="any", session_id="s1")
    assert "point out all the major features" in out, out
    assert "Continue the prior conversation" not in out, out


@pytest.mark.asyncio
async def test_fallback_without_context_is_honest(config):
    summarizer = ConversationSummarizer(config, _FailingProvider())
    out = await summarizer.summarize([], model="any", session_id="s1")
    assert out == ""  # empty input short-circuits; no fabricated objective


def test_merge_run_state_resets_findings():
    from server.agents.run_state import SessionRunState

    previous = SessionRunState(
        findings=["Run failed: Connection error."],
        todo=[{"id": "t1", "title": "Ship", "status": "pending"}],
        plan="# plan",
    )
    fresh = merge_run_state(previous, ts=1.0)
    assert fresh.findings == [], "stale findings leaked into the new run"
    assert fresh.todo == previous.todo, "todos must carry over"
    assert fresh.plan == previous.plan, "plan must carry over"
