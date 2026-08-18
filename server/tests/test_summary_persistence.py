from __future__ import annotations

import pytest

from server.agents.loop import AgentLoop
from server.agents.prompt_executor import PromptExecutor
from server.config.settings import AppSettings
from server.domain.domain import ScenarioMode
from server.domain.session import Session
from server.persistence.repositories.sessions import MessageRepository, SessionRepository
from server.providers.base import BaseProvider, ProviderResponse


class MockSummaryProvider(BaseProvider):
    def __init__(self, name: str = "mock"):
        super().__init__(name, model="mock-model", max_tokens=100, temperature=0.7)

    async def generate(self, messages: list[dict], **kwargs) -> ProviderResponse:
        return ProviderResponse(content="Hello back!", raw_response={})

    async def complete(self, messages: list[dict], tools=None) -> str:
        return "Hello back!"

    async def stream(
        self, messages: list[dict], tools=None, tool_choice=None, response_format=None
    ):
        yield ("Hello back!", None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["mock-model"]


@pytest.mark.asyncio
async def test_summary_rehydration_and_persistence(db, tmp_path):
    session_repo = SessionRepository(db)
    message_repo = MessageRepository(db)

    # 1. Create a session with a persisted summary
    session = Session(
        id="test-summary-sess-1",
        title="Test Session",
        mode=ScenarioMode.BUILD,
        metadata={"summary": "Previous summary: user built FastAPI app."},
    )
    await session_repo.create(session)

    config = AppSettings(workspace_root=str(tmp_path))
    provider = MockSummaryProvider()

    from server.skills.loader import SkillLoader
    from server.toolkit import create_default_registry

    executor = PromptExecutor(
        config,
        provider,
        create_default_registry(),
        session_repo,
        message_repo,
        SkillLoader(str(config.workspace_root)),
    )

    # 2. Execute prompt; the completed turn schedules a background running summary.
    await executor._execute("test-summary-sess-1", "Hi", "build", None, None)

    # 3. Await the background summary task so no DB I/O outlives the test teardown.
    task = executor._summary_scheduler._tasks.get("test-summary-sess-1")
    if task is not None:
        await task

    # 4. The async running summary refreshed the persisted session summary
    #    (todo 3.13-3.14: per-turn write-back, freshest wins).
    db_sess = await session_repo.get("test-summary-sess-1")
    assert db_sess is not None
    assert db_sess.metadata.get("summary") == "Hello back!"

    # 5. Simulate summary update in agent loop
    agent = AgentLoop(config, provider)
    agent.set_summary("Updated summary: user asked for help.")

    # 6. Manual write-back still lands and rehydrates.
    db_sess.metadata["summary"] = agent.summary
    await session_repo.update(db_sess)

    # Re-fetch and check
    reloaded = await session_repo.get("test-summary-sess-1")
    assert reloaded is not None
    assert reloaded.metadata.get("summary") == "Updated summary: user asked for help."
