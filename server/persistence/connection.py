from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from server.config.constants import SQLITE_BUSY_TIMEOUT_MS

logger = logging.getLogger(__name__)
for _noisy in ("sqlalchemy", "sqlalchemy.engine", "sqlalchemy.engine.Engine", "aiosqlite"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


def resolve_db_path() -> str:
    return os.getenv("ZENITH_DB_PATH", "data/zenith.db")


def _set_pragmas(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


class Database:
    def __init__(self, db_path: str = "data/zenith.db"):
        self.db_path = db_path
        self.startup_result: dict | None = None
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._connection: AsyncConnection | None = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def connect(self) -> None:
        from .startup import DatabaseStartupService

        service = DatabaseStartupService(self.db_path)
        self.startup_result = service.run()
        from server.persistence.crypto import encryption_enabled

        if not encryption_enabled():
            logger.info(
                "Encryption at rest is NOT enabled (set ZENITH_ENCRYPTION_KEY to enable)"
            )
        self._engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(self.db_path).resolve()}",
            echo=os.getenv("ZENITH_LOG_LEVEL", "").lower() == "debug",
            pool_pre_ping=True,
        )
        event.listen(self._engine.sync_engine, "connect", _set_pragmas)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        logger.info("Database connected: %s", self.db_path)

    async def close(self) -> None:
        if self._connection is not None:
            try:
                await self._connection.close()
            except Exception:
                pass
            self._connection = None
        if self._engine is not None:
            try:
                await self._engine.dispose()
            except Exception:
                pass
            self._engine = None
            self._session_factory = None
            logger.info("Database closed: %s", self.db_path)

    @property
    def connected(self) -> bool:
        return self._engine is not None

    def session(self) -> AsyncSession:
        if self._session_factory is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._session_factory()

    async def health_check(self) -> bool:
        if self._engine is None:
            return False
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def get_current_version(self) -> str | None:
        from .startup import get_current_version

        return get_current_version(self.db_path)

    async def _ensure_connection(self) -> AsyncConnection:
        if self._engine is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        if self._connection is None:
            self._connection = await self._engine.connect()
        return self._connection

    async def _reconnect(self) -> AsyncConnection:
        if self._connection is not None:
            try:
                await self._connection.close()
            except Exception:
                pass
            self._connection = None
        return await self._ensure_connection()

    async def execute(self, sql: str, params: tuple = ()):
        conn = await self._ensure_connection()
        try:
            return await conn.exec_driver_sql(sql, params)
        except OperationalError:
            logger.warning("Database connection lost, reconnecting...")
            conn = await self._reconnect()
            return await conn.exec_driver_sql(sql, params)

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        result = await self.execute(sql, params)
        row = result.mappings().first()
        return dict(row) if row else None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        result = await self.execute(sql, params)
        return [dict(r) for r in result.mappings().all()]

    async def commit(self):
        conn = await self._ensure_connection()
        await conn.commit()
