-- 002: metadata columns (created_by / updated_by / is_deleted)
--
-- Adds auditing columns to the four core tables that mirror the legacy
-- Alembic revision 0002_metadata_columns. SQLite only supports adding
-- columns; NOT NULL columns require a server default, and PRIMARY KEY /
-- UNIQUE columns cannot be added. All three columns on all four tables are
-- nullable-or-defaulted accordingly.

ALTER TABLE sessions ADD COLUMN created_by TEXT;
ALTER TABLE sessions ADD COLUMN updated_by TEXT;
ALTER TABLE sessions ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0;

ALTER TABLE providers ADD COLUMN created_by TEXT;
ALTER TABLE providers ADD COLUMN updated_by TEXT;
ALTER TABLE providers ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0;

ALTER TABLE permissions ADD COLUMN created_by TEXT;
ALTER TABLE permissions ADD COLUMN updated_by TEXT;
ALTER TABLE permissions ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0;

ALTER TABLE budget_settings ADD COLUMN created_by TEXT;
ALTER TABLE budget_settings ADD COLUMN updated_by TEXT;
ALTER TABLE budget_settings ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0;
