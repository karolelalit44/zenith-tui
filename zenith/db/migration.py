"""Migration runner — applies numbered SQL migrations to the database."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class MigrationRunner:
    def __init__(self, db: "Database") -> None:
        self.db = db

    async def ensure_migrations_table(self) -> None:
        await self.db.execute(
            "CREATE TABLE IF NOT EXISTS _migrations ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  name TEXT NOT NULL UNIQUE,"
            "  applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        await self.db.commit()

    async def get_applied(self) -> set[str]:
        rows = await self.db.fetch_all("SELECT name FROM _migrations ORDER BY id")
        return {r["name"] for r in rows}

    async def run_all(self) -> list[str]:
        await self.ensure_migrations_table()
        applied = await self.get_applied()
        if not MIGRATIONS_DIR.exists():
            logger.info("No migrations directory at %s", MIGRATIONS_DIR)
            return []

        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        results: list[str] = []

        for filepath in files:
            if filepath.name in applied:
                continue
            sql = filepath.read_text(encoding="utf-8")
            try:
                await self.db.execute("BEGIN TRANSACTION")
                await self.db._connection.executescript(sql)
                await self.db.execute(
                    "INSERT INTO _migrations (name) VALUES (?)",
                    (filepath.name,),
                )
                await self.db.commit()
                logger.info("Applied migration: %s", filepath.name)
                results.append(filepath.name)
            except Exception as e:
                msg = str(e).lower()
                if "duplicate column" in msg:
                    await self.db.execute(
                        "INSERT INTO _migrations (name) VALUES (?)",
                        (filepath.name,),
                    )
                    await self.db.commit()
                    logger.info("Migration %s already applied (columns exist): %s", filepath.name, e)
                    results.append(filepath.name)
                else:
                    await self.db.execute("ROLLBACK")
                    logger.error("Migration %s failed: %s", filepath.name, e)
                    raise

        return results
