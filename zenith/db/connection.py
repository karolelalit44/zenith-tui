import logging
import aiosqlite
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = "zenith.db"):
        self.db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self):
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        schema = SCHEMA_PATH.read_text()
        await self._connection.executescript(schema)
        await self._connection.commit()
        await self._run_migrations()

    async def _run_migrations(self) -> None:
        from .migration import MigrationRunner

        runner = MigrationRunner(self)
        applied = await runner.run_all()
        if applied:
            logger.info("Applied %d migration(s): %s", len(applied), ", ".join(applied))

    async def close(self):
        if self._connection:
            await self._connection.close()

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        assert self._connection is not None
        return await self._connection.execute(sql, params)

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        cursor = await self.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = await self.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def commit(self):
        assert self._connection is not None
        await self._connection.commit()
