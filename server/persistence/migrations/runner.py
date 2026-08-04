from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from server.domain.errors import MigrationError

from ..logging import db_log

logger = logging.getLogger(__name__)
SQL_DIR = Path(__file__).parent / "sql"
TRACKING_TABLE = "schema_migrations"
_FILENAME_RE = re.compile("^(\\d{3})_(.+)\\.sql$")
MigrationInfo = dict


def _sqlite_tables(db_path: str) -> set[str]:
    if not Path(db_path).exists() or Path(db_path).stat().st_size == 0:
        return set()
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def discover(sql_dir: Path | str | None = None) -> list[MigrationInfo]:
    directory = Path(sql_dir) if sql_dir else SQL_DIR
    if not directory.exists():
        logger.warning("Migration directory not found: %s", directory)
        return []
    migrations: list[MigrationInfo] = []
    for f in sorted(directory.glob("*.sql")):
        m = _FILENAME_RE.match(f.name)
        if not m:
            logger.warning("Ignoring migration file with invalid name: %s", f.name)
            continue
        migrations.append(
            {
                "version": m.group(1),
                "title": m.group(2).replace("_", " "),
                "filename": f.name,
                "path": f,
            }
        )
    return migrations


def get_applied(db_path: str) -> list[str]:
    if TRACKING_TABLE not in _sqlite_tables(db_path):
        return []
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(f"SELECT version FROM {TRACKING_TABLE} ORDER BY version").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def get_current_version(db_path: str) -> str | None:
    applied = get_applied(db_path)
    return applied[-1] if applied else None


def ensure_tracking_table(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {TRACKING_TABLE} (version TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', applied_at TEXT NOT NULL)"
        )
        conn.commit()
    finally:
        conn.close()


def stamp(db_path: str, version: str, title: str = "") -> None:
    ensure_tracking_table(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            f"INSERT OR IGNORE INTO {TRACKING_TABLE} (version, title, applied_at) VALUES (?, ?, ?)",
            (version, title, datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _apply_file(db_path: str, migration: MigrationInfo) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(migration["path"].read_text(encoding="utf-8"))
        conn.execute(
            f"INSERT INTO {TRACKING_TABLE} (version, title, applied_at) VALUES (?, ?, ?)",
            (migration["version"], migration["title"], datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def run_pending(db_path: str) -> list[MigrationInfo]:
    applied = set(get_applied(db_path))
    pending = [m for m in discover() if m["version"] not in applied]
    results: list[MigrationInfo] = []
    for m in pending:
        try:
            _apply_file(db_path, m)
        except Exception as e:
            db_log(
                "migrate",
                status="error",
                version=m["version"],
                file=m["filename"],
                error=str(e),
                db=str(db_path),
            )
            raise MigrationError(
                f"Migration {m['version']} ({m['filename']}) failed for '{db_path}': {e}", cause=e
            ) from e
        db_log("migrate", status="ok", version=m["version"], file=m["filename"], db=str(db_path))
        logger.info("Applied migration %s (%s)", m["version"], m["filename"])
        results.append(m)
    return results
