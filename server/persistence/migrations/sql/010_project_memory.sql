-- 010_project_memory.sql
-- Project-level memory store (cross-session learnings).

CREATE TABLE IF NOT EXISTS project_memory (
    id          TEXT PRIMARY KEY,
    workspace_root TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_project_memory_ws_key
    ON project_memory (workspace_root, key);

CREATE INDEX IF NOT EXISTS idx_project_memory_ws
    ON project_memory (workspace_root);
