-- 009: session workspace persistence
--
-- Persists the in-process session file registry to disk so that file tracking
-- (writes, edits, reads, staleness) survives server restarts. Each row tracks
-- one file touched during a session with its content hash, size, operation
-- counts, and monotonic timestamps for staleness detection.

CREATE TABLE IF NOT EXISTS session_workspace (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    path        TEXT NOT NULL,
    content_hash TEXT NOT NULL DEFAULT '',
    size        INTEGER NOT NULL DEFAULT 0,
    writes      INTEGER NOT NULL DEFAULT 0,
    edits       INTEGER NOT NULL DEFAULT 0,
    last_read_at    REAL NOT NULL DEFAULT 0.0,
    last_edited_at  REAL NOT NULL DEFAULT 0.0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_session_workspace_session_path
    ON session_workspace (session_id, path);

CREATE INDEX IF NOT EXISTS idx_session_workspace_session
    ON session_workspace (session_id);
