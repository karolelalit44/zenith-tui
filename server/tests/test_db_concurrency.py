from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from server.domain.domain import ScenarioMode, SessionState
from server.domain.message import Message
from server.domain.session import Session
from server.persistence.connection import Database
from server.persistence.repositories.misc import AppSettingsRepository
from server.persistence.repositories.sessions import MessageRepository, SessionRepository


class TestDatabaseConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_sessions_and_messages_write_stress(self, temp_dir: Path):
        db_path = str(temp_dir / "concurrency_stress.db")
        db = Database(db_path)
        await db.connect()
        try:
            session_repo = SessionRepository(db)
            message_repo = MessageRepository(db)
            config_repo = AppSettingsRepository(db)

            async def _worker(worker_id: int):
                sess_id = f"concurrent-sess-{worker_id}"
                session = Session(
                    id=sess_id,
                    title=f"Concurrent Worker {worker_id}",
                    mode=ScenarioMode.BUILD,
                    state=SessionState.CREATED,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    model="gemini-3.5-flash-lite",
                    provider="google",
                    total_tokens=100 * worker_id,
                )
                await session_repo.create(session)

                for msg_idx in range(5):
                    msg = Message(
                        id=f"msg-{worker_id}-{msg_idx}",
                        session_id=sess_id,
                        role="user" if msg_idx % 2 == 0 else "assistant",
                        content=f"Message {msg_idx} from worker {worker_id}",
                        token_count=20,
                        created_at=datetime.now(),
                    )
                    await message_repo.create(msg)
                    await config_repo.set(f"worker_{worker_id}_status", f"step_{msg_idx}")

                # Verify reads during write pressure
                msgs = await message_repo.get_by_session(sess_id)
                assert len(msgs) == 5

            # Run 10 workers in parallel
            tasks = [_worker(i) for i in range(10)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for idx, res in enumerate(results):
                if isinstance(res, Exception):
                    pytest.fail(f"Worker {idx} failed with: {res}")

            # Verify total sessions in database
            all_sessions = await session_repo.list()
            assert len(all_sessions) >= 10
        finally:
            await db.close()
