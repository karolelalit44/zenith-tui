"""SQL-file migration runner — versioned schema changes without Python.

How it works:

- Each migration is a plain SQL file named ``NNN_title.sql`` in ``sql/``
  (``NNN`` is a zero-padded serial, ``title`` a short underscore name).
- The runner discovers those files, sorts them by serial, and applies the
  ones that have not been recorded yet, in order, on the target database.
- Applied files are recorded in the ``schema_migrations`` table
  (``version`` PK, ``title``, ``applied_at``), one row per file.
- ``migrate`` applies pending files; ``current`` shows the highest applied
  serial; ``history`` lists all files with applied/pending status.

Failure behaviour: a file that raises is logged, NOT recorded, and the run
stops — the command reports pass/fail per file. Because SQLite DDL is
non-transactional, a failed file may leave partial DDL behind; reconcile
manually (or make the file idempotent) and re-run.

No Python code runs per migration — these files are plain SQL executed
directly against the database.
"""

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
_FILENAME_RE = re.compile(r"^(\d{3})_(.+)\.sql$")

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
    """Return all migrations found on disk, sorted by serial number.

    Each item is ``{"version", "title", "filename", "path"}``.
    """
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
    """Return the list of applied versions (recorded in the tracking table)."""
    if TRACKING_TABLE not in _sqlite_tables(db_path):
        return []
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(f"SELECT version FROM {TRACKING_TABLE} ORDER BY version").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def get_current_version(db_path: str) -> str | None:
    """Return the highest applied version, or None when not migrated."""
    applied = get_applied(db_path)
    return applied[-1] if applied else None


def ensure_tracking_table(db_path: str) -> None:
    """Create the tracking table if it does not exist (safe to call always)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS {TRACKING_TABLE} (
                version    TEXT PRIMARY KEY,
                title      TEXT NOT NULL DEFAULT '',
                applied_at TEXT NOT NULL
            )"""
        )
        conn.commit()
    finally:
        conn.close()


def stamp(db_path: str, version: str, title: str = "") -> None:
    """Record a migration as applied WITHOUT running its SQL.

    Used to adopt databases whose schema already matches an existing
    migration (e.g. a legacy pre-runner database equal to the baseline, or an
    Alembic-versioned database whose revisions map to files 001/002).
    """
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
    """Apply every discovered migration not yet recorded, in order.

    Returns the list of migrations that were applied. Raises ``MigrationError``
    on the first file that fails (that file is left un-recorded).
    """
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
                f"Migration {m['version']} ({m['filename']}) failed for '{db_path}': {e}",
                cause=e,
            ) from e
        db_log(
            "migrate",
            status="ok",
            version=m["version"],
            file=m["filename"],
            db=str(db_path),
        )
        logger.info("Applied migration %s (%s)", m["version"], m["filename"])
        results.append(m)
    return results
