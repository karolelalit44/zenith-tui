"""Todo 3.13-3.14: async running summary scheduler.

A completed turn schedules a weak-model summary in the background (non-blocking);
on completion the fresh summary is written back to the session metadata. The next
prompt prefers that summary and falls back to the last persisted one while a write
is pending. Late-arriving stale summaries (a newer turn was scheduled while an
older one was in flight) are dropped so ordering stays deterministic.
"""

import asyncio

from server.agents.running_summary import RunningSummaryScheduler
from server.config.constants import RUNNING_SUMMARY_MESSAGE_LIMIT
from server.config.settings import AppSettings
from server.domain.message import Message
from server.domain.session import Session
from server.providers.base import BaseProvider


class _FakeProvider(BaseProvider):
    def __init__(self, results: list[tuple[float, str]]):
        super().__init__("test", "test-model")
        self.results = list(results)
        self.calls = 0
        self.last_prompt = ""
        self.block_first: asyncio.Event | None = None
        self.first_started = asyncio.Event()

    async def complete(self, messages, tools=None, model=None) -> str:
        self.calls += 1
        if self.block_first is not None and self.calls == 1:
            self.first_started.set()
            await self.block_first.wait()
        delay, text = self.results.pop(0) if self.results else (0.0, "")
        if delay:
            await asyncio.sleep(delay)
        self.last_prompt = messages[-1]["content"]
        return text

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        return
        yield

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["test-model"]


class _FakeMessageRepo:
    def __init__(self, messages: list[Message]):
        self.messages = messages
        self.limit = None

    async def get_by_session(self, session_id: str, limit: int = 50) -> list[Message]:
        self.limit = limit
        return self.messages


class _FakeSessionRepo:
    def __init__(self, session: Session):
        self.session = session
        self.updates = 0

    async def get(self, session_id: str) -> Session | None:
        return self.session

    async def update(self, session: Session) -> Session:
        self.updates += 1
        self.session = session
        return session


def _build(
    async_summary_enabled: bool = True,
) -> tuple[RunningSummaryScheduler, _FakeProvider, _FakeMessageRepo, _FakeSessionRepo]:
    config = AppSettings(
        home_dir="data/test.db",
        workspace_root=".",
        weak_model=None,
        async_summary_enabled=async_summary_enabled,
    )
    provider = _FakeProvider([])
    messages = [
        Message(session_id="s1", role="user", content="build the auth module"),
        Message(session_id="s1", role="assistant", content="creating auth.py"),
    ]
    session = Session(id="s1", metadata={"summary": "OLD"})
    message_repo = _FakeMessageRepo(messages)
    session_repo = _FakeSessionRepo(session)
    scheduler = RunningSummaryScheduler(config, provider, session_repo, message_repo)
    return scheduler, provider, message_repo, session_repo


async def test_schedules_background_task_and_persists_fresh_summary():
    scheduler, provider, message_repo, session_repo = _build()
    provider.results = [(0.0, "OBJECTIVE: auth done")]

    scheduler.schedule("s1")

    assert isinstance(scheduler._tasks["s1"], asyncio.Task)
    await scheduler._tasks["s1"]
    assert session_repo.session.metadata["summary"] == "OBJECTIVE: auth done"
    assert session_repo.updates == 1
    assert message_repo.limit == RUNNING_SUMMARY_MESSAGE_LIMIT


async def test_previous_summary_is_anchored_and_model_passed():
    scheduler, provider, message_repo, session_repo = _build()
    provider.results = [(0.0, "OBJECTIVE: merged")]

    scheduler.schedule("s1")
    await scheduler._tasks["s1"]

    assert "OLD" in provider.last_prompt


async def test_stale_summary_from_older_turn_is_dropped():
    scheduler, provider, message_repo, session_repo = _build()
    provider.results = [(0.0, "GEN1"), (0.0, "GEN2")]
    provider.block_first = asyncio.Event()

    scheduler.schedule("s1")  # gen 1: blocks mid-flight
    first = scheduler._tasks["s1"]
    await provider.first_started.wait()

    scheduler.schedule("s1")  # gen 2 supersedes gen 1 before it applies
    second = scheduler._tasks["s1"]
    provider.block_first.set()  # now release gen 1; its write is stale
    await second
    await first

    assert session_repo.session.metadata["summary"] == "GEN2"
    assert session_repo.updates == 1


async def test_superseded_before_start_never_calls_provider():
    scheduler, provider, message_repo, session_repo = _build()
    provider.results = [(0.0, "GEN2")]

    scheduler.schedule("s1")  # gen 1
    scheduler.schedule("s1")  # gen 2 supersedes before gen 1 starts

    await scheduler._tasks["s1"]
    await asyncio.sleep(0)

    assert provider.calls == 1
    assert session_repo.session.metadata["summary"] == "GEN2"
    assert session_repo.updates == 1


async def test_disabled_scheduler_does_nothing():
    scheduler, provider, message_repo, session_repo = _build(async_summary_enabled=False)

    scheduler.schedule("s1")
    await asyncio.sleep(0)

    assert scheduler._tasks == {}
    assert provider.calls == 0
    assert session_repo.updates == 0
    assert session_repo.session.metadata["summary"] == "OLD"


async def test_no_messages_skips_write():
    scheduler, provider, message_repo, session_repo = _build()
    message_repo.messages = []
    provider.results = [(0.0, "OBJECTIVE: should not run")]

    scheduler.schedule("s1")
    await scheduler._tasks["s1"]

    assert provider.calls == 0
    assert session_repo.updates == 0


async def test_empty_summary_skips_write():
    scheduler, provider, message_repo, session_repo = _build()
    provider.results = [(0.0, "")]

    scheduler.schedule("s1")
    await scheduler._tasks["s1"]

    assert provider.calls == 1
    assert session_repo.updates == 0
    assert session_repo.session.metadata["summary"] == "OLD"
