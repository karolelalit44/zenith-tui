from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

from server.domain.errors import MigrationError

from .logging import db_log
from .migrations import runner

logger = logging.getLogger(__name__)
EXPECTED_LEGACY = {
    "002_providers_and_models.sql",
    "003_provider_capabilities.sql",
    "004_session_plan_fields.sql",
    "005_token_usage.sql",
    "006_token_usage_v2.sql",
    "007_estimated_token_usage.sql",
    "008_session_state_machine.sql",
    "009_permissions.sql",
    "010_search_index.sql",
}


def _sqlite_tables(db_path: str) -> set[str]:
    if not Path(db_path).exists() or Path(db_path).stat().st_size == 0:
        return set()
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def get_current_version(db_path: str) -> str | None:
    return runner.get_current_version(db_path)


class DatabaseStartupService:
    def __init__(self, db_path: str) -> None:
        self.db_path = str(db_path)
        self.current_version: str | None = None
        self.mode: str = "none"
        self.applied: list[str] = []

    def run(self) -> dict:
        start = time.perf_counter()
        db_path = self.db_path
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        tables = _sqlite_tables(db_path)
        has_legacy = "_migrations" in tables
        has_alembic = "alembic_version" in tables
        has_schema = runner.TRACKING_TABLE in tables
        if not tables:
            self.mode = "fresh"
        elif has_schema:
            self.mode = "current"
        elif has_legacy:
            self.mode = "legacy"
        elif has_alembic:
            self.mode = "alembic"
        else:
            self.mode = "unmanaged"
        try:
            if self.mode == "fresh":
                self._handle_fresh(db_path)
            elif self.mode == "legacy":
                self._handle_legacy(db_path)
            elif self.mode == "alembic":
                self._handle_alembic(db_path)
            elif self.mode == "current":
                self._handle_current(db_path)
            else:
                raise MigrationError(
                    f"Database '{db_path}' has tables but no _migrations, alembic_version, or schema_migrations — cannot determine migration state"
                )
            self.current_version = get_current_version(db_path)
            self._parity_check(db_path)
        except MigrationError:
            raise
        except Exception as e:
            raise MigrationError(f"Migration failed for '{db_path}': {e}", cause=e) from e
        duration_ms = (time.perf_counter() - start) * 1000.0
        db_log(
            "migrate",
            status="ok",
            duration_ms=duration_ms,
            version=self.current_version or "",
            mode=self.mode,
            applied=",".join(self.applied) if self.applied else "none",
            db=self.db_path,
        )
        logger.info(
            "Database startup complete: mode=%s version=%s applied=%s path=%s",
            self.mode,
            self.current_version,
            self.applied or "none",
            self.db_path,
        )
        return {
            "db_path": self.db_path,
            "mode": self.mode,
            "version": self.current_version,
            "applied": self.applied,
            "duration_ms": round(duration_ms, 2),
        }

    def _handle_fresh(self, db_path: str) -> None:
        db_log("migrate", status="ok", mode="fresh", note="creating_new_database")
        runner.ensure_tracking_table(db_path)
        applied = runner.run_pending(db_path)
        self.applied = [m["version"] for m in applied]

    def _handle_legacy(self, db_path: str) -> None:
        db_log("migrate", status="ok", mode="legacy", note="stamping_baseline")
        baseline = next((m for m in runner.discover() if m["version"] == "001"), None)
        if baseline is None:
            raise MigrationError("Baseline migration 001 not found on disk")
        runner.stamp(db_path, "001", baseline["title"])
        self.applied.append("001 (stamp)")
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("DROP TABLE _migrations")
            conn.commit()
        finally:
            conn.close()
        db_log("migrate", status="ok", mode="legacy", note="dropped_legacy_table")
        for m in runner.run_pending(db_path):
            self.applied.append(m["version"])

    def _handle_alembic(self, db_path: str) -> None:
        version_num = _read_alembic_version(db_path)
        db_log(
            "migrate", status="ok", mode="alembic", note="stamping_revisions", version=version_num
        )
        stamped = 0
        for m in runner.discover():
            if int(m["version"]) <= int(version_num):
                runner.stamp(db_path, m["version"], m["title"])
                stamped += 1
                self.applied.append(f"{m['version']} (stamp)")
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("DROP TABLE alembic_version")
            conn.commit()
        finally:
            conn.close()
        db_log(
            "migrate", status="ok", mode="alembic", note="dropped_alembic_version", stamped=stamped
        )
        for m in runner.run_pending(db_path):
            self.applied.append(m["version"])

    def _handle_current(self, db_path: str) -> None:
        db_log("migrate", status="ok", mode="current", note="apply_pending")
        for m in runner.run_pending(db_path):
            self.applied.append(m["version"])

    def _parity_check(self, db_path: str) -> None:
        from .models import Base

        existing = _sqlite_tables(db_path)
        expected = set(Base.metadata.tables)
        missing = expected - existing
        if missing:
            raise MigrationError(
                f"Post-migration parity check failed: missing tables {sorted(missing)}"
            )
        db_log("parity", status="ok", table="*", count=len(expected))


def _read_alembic_version(db_path: str) -> str:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        version = row[0] if row else ""
    finally:
        conn.close()
    if not version:
        raise MigrationError("alembic_version table exists but is empty")
    return version
