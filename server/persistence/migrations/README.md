# SQL-File Migrations — Conventions

Schema is version-controlled here as plain SQL files in `sql/`. A lightweight
runner (`runner.py`) applies them in serial order on server start and records
progress in the `schema_migrations` table. No Python code runs per migration —
a migration is exactly one `.sql` file.

## Commands

| What | Command |
|---|---|
| Create a fresh DB up to head | `python -m server.main db init` |
| Apply pending migrations | `python -m server.main db migrate` (also runs on server start) |
| Show current version | `python -m server.main db current` |
| Show every file + applied/pending status | `python -m server.main db history` |
| Roll back | not supported — see "Downgrades" below |

The runner records applied files in the `schema_migrations` table
(`version` PK, `title`, `applied_at`).

## Adding a migration

1. Create `sql/NNN_title.sql` where `NNN` is the next serial (zero-padded) and
   `title` is a short snake_case name, e.g. `003_session_archives.sql`.
2. Write the forward SQL — `CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX`,
   `INSERT`, etc. — executed directly against the target database.
3. Run `python -m server.main db migrate --db-path <your-db>` and confirm the
   file is listed as applied and the parity check passes.

## Conventions

1. **Serials** increase monotonically and uniquely identify each migration.
   Never renumber an existing file once it has shipped.
2. **Immutability** — a committed migration is never edited. Schema drift is
   fixed with a *new* migration, never by rewriting an old one. (`001` is a
   one-time baseline of the pre-runner schema.)
3. **One logical change per migration** — a migration that adds columns,
   creates a table, or backfills data each gets its own file.
4. **Downgrades** — not supported. There is no `downgrade()`; if you need to
   undo a schema change, write a forward migration that reverses it. The
   `downgrade` CLI command exists only to say so.
5. **SQLite limits** — `ALTER TABLE ADD COLUMN` cannot add `PRIMARY KEY`,
   `UNIQUE`, or `FOREIGN KEY` columns and cannot add a `NOT NULL` column
   without a server default. Use `CREATE TABLE` + copy for such changes.
6. **FTS5** — virtual tables (`message_fts`, `session_fts`) are not
   ORM-representable. They are created in SQL and kept in sync via triggers.
   Do not modify them in ORM models.
7. **Defaults** — SQLite columns use DDL-level defaults (matching the ORM
   `server_default`), not Python-side defaults.
8. **Failure behaviour** — a failed file is reported and left un-recorded;
   the run stops. Because SQLite DDL is non-transactional, a failed file may
   leave partial DDL behind. Reconcile manually (or make the file idempotent
   with `IF NOT EXISTS`), then re-run.
9. **Adoption** — databases that predate the runner are adopted automatically
   by `DatabaseStartupService`: legacy `_migrations` DBs are stamped at the
   baseline (`001`), Alembic-versioned DBs are stamped up to their recorded
   revision, and both old tracking tables are dropped.
10. **Verification** — after writing a migration, run
    `python -m server.main db migrate` against a copy of `data/zenith.db` and
    confirm the boot log shows a successful run + parity check.
