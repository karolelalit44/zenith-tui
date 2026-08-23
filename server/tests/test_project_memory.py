"""Tests for Gap #7: project memory repository and context injection."""

from __future__ import annotations

from pathlib import Path

import pytest

from server.agents.context import ContextManager, TIER_T1
from server.config.settings import AppSettings
from server.domain.message import Message
from server.storage.memory_store import (
    MAX_PROJECT_MEMORY_ENTRIES,
    FileProjectMemoryRepository,
)
from server.storage.paths import StorageHome

SYSTEM_PROMPT = "You are Zenith, a coding agent." * 50


def _base_config(**kwargs) -> AppSettings:
    defaults = dict(
        repo_map_enabled=False,
        memory_enabled=False,
    )
    defaults.update(kwargs)
    return AppSettings(**defaults)


@pytest.fixture()
def repo(temp_dir) -> FileProjectMemoryRepository:
    return FileProjectMemoryRepository(StorageHome(temp_dir))


class TestProjectMemoryRepository:
    async def test_upsert_and_get(self, repo: FileProjectMemoryRepository):
        await repo.upsert("/workspace", "pytest_mode", "asyncio_mode=auto")
        val = await repo.get_value("/workspace", "pytest_mode")
        assert val == "asyncio_mode=auto"

    async def test_upsert_updates_existing(self, repo: FileProjectMemoryRepository):
        await repo.upsert("/ws", "key", "v1")
        await repo.upsert("/ws", "key", "v2")
        val = await repo.get_value("/ws", "key")
        assert val == "v2"

    async def test_get_all(self, repo: FileProjectMemoryRepository):
        await repo.upsert("/ws", "a", "1")
        await repo.upsert("/ws", "b", "2")
        records = await repo.get_all("/ws")
        assert len(records) == 2
        keys = {r.key for r in records}
        assert keys == {"a", "b"}

    async def test_delete(self, repo: FileProjectMemoryRepository):
        await repo.upsert("/ws", "del", "me")
        deleted = await repo.delete("/ws", "del")
        assert deleted is True
        assert await repo.get_value("/ws", "del") is None

    async def test_delete_nonexistent(self, repo: FileProjectMemoryRepository):
        deleted = await repo.delete("/ws", "nope")
        assert deleted is False

    async def test_workspace_isolation(self, repo: FileProjectMemoryRepository):
        await repo.upsert("/ws1", "k", "v1")
        await repo.upsert("/ws2", "k", "v2")
        assert await repo.get_value("/ws1", "k") == "v1"
        assert await repo.get_value("/ws2", "k") == "v2"

    async def test_eviction_at_cap(self, repo: FileProjectMemoryRepository):
        for i in range(MAX_PROJECT_MEMORY_ENTRIES + 2):
            await repo.upsert("/ws", f"key_{i}", f"val_{i}")
        records = await repo.get_all("/ws")
        assert len(records) == MAX_PROJECT_MEMORY_ENTRIES


class TestProjectMemoryContextInjection:
    def test_project_memory_injected_as_t1(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        messages = ctx.build_messages(
            [Message(session_id="s1", role="assistant", content="ok")],
            SYSTEM_PROMPT,
            "continue",
            "gpt-4",
            project_memory="- pytest_mode: asyncio_mode=auto",
        )
        pm_msgs = [m for m in messages if "<project_memory>" in m.get("content", "")]
        assert len(pm_msgs) == 1
        tiers = ctx.tiers()
        pm_idx = messages.index(pm_msgs[0])
        assert tiers[pm_idx] == TIER_T1

    def test_empty_project_memory_not_injected(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        messages = ctx.build_messages(
            [Message(session_id="s1", role="assistant", content="ok")],
            SYSTEM_PROMPT,
            "continue",
            "gpt-4",
        )
        pm_msgs = [m for m in messages if "<project_memory>" in m.get("content", "")]
        assert len(pm_msgs) == 0

    def test_project_memory_in_fresh_session(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        messages = ctx.build_messages(
            [],
            SYSTEM_PROMPT,
            "start",
            "gpt-4",
            project_memory="- rule: no globals",
        )
        pm_msgs = [m for m in messages if "<project_memory>" in m.get("content", "")]
        assert len(pm_msgs) == 1
