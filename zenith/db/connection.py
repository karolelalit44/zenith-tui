import logging
import os
import aiosqlite
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

logger = logging.getLogger(__name__)


def resolve_db_path() -> str:
    return os.getenv("ZENITH_DB_PATH", "zenith.db")


class Database:
    def __init__(self, db_path: str = "zenith.db"):
        self.db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def connect(self):
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        schema = SCHEMA_PATH.read_text()
        await self._connection.executescript(schema)
        await self._connection.commit()
        await self._run_migrations()
        logger.info("Database connected: %s", self.db_path)

    async def _ensure_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        try:
            await self._connection.execute("SELECT 1")
        except Exception:
            logger.warning("Database connection lost, reconnecting...")
            await self.connect()
        assert self._connection is not None
        return self._connection

    async def _run_migrations(self) -> None:
        from .migration import MigrationRunner

        runner = MigrationRunner(self)
        applied = await runner.run_all()
        if applied:
            logger.info("Applied %d migration(s): %s", len(applied), ", ".join(applied))

    async def close(self):
        if self._connection:
            try:
                await self._connection.close()
            except Exception:
                pass
            self._connection = None
            logger.info("Database closed: %s", self.db_path)

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        conn = await self._ensure_connection()
        return await conn.execute(sql, params)

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        cursor = await self.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = await self.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def commit(self):
        conn = await self._ensure_connection()
        await conn.commit()
