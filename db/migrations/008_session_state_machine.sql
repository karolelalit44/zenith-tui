-- Migration 008: Add columns and tables for expanded session state machine

-- Add new columns to sessions table (each may fail if already present)
ALTER TABLE sessions ADD COLUMN provider TEXT;
ALTER TABLE sessions ADD COLUMN model TEXT;
ALTER TABLE sessions ADD COLUMN agent_state TEXT NOT NULL DEFAULT 'idle';
ALTER TABLE sessions ADD COLUMN total_cost REAL NOT NULL DEFAULT 0.0;
ALTER TABLE sessions ADD COLUMN context_used INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sessions ADD COLUMN context_window INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sessions ADD COLUMN context_percent REAL NOT NULL DEFAULT 0.0;
ALTER TABLE sessions ADD COLUMN error_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sessions ADD COLUMN last_error TEXT;
ALTER TABLE sessions ADD COLUMN export_format TEXT;
ALTER TABLE sessions ADD COLUMN exported_at TEXT;

-- New tables
CREATE TABLE IF NOT EXISTS session_checkpoints (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    checkpoint_type TEXT NOT NULL DEFAULT 'automatic',
    step_index INTEGER NOT NULL DEFAULT 0,
    snapshot_data TEXT NOT NULL DEFAULT '{}',
    token_count INTEGER NOT NULL DEFAULT 0,
    message_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    event_data TEXT NOT NULL DEFAULT '{}',
    sequence INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_status_history (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    from_state TEXT,
    to_state TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_drafts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    prompt TEXT NOT NULL DEFAULT '',
    context TEXT NOT NULL DEFAULT '{}',
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_checkpoints_session ON session_checkpoints(session_id);
CREATE INDEX IF NOT EXISTS idx_sync_events_session_seq ON sync_events(session_id, sequence);
CREATE INDEX IF NOT EXISTS idx_status_history_session ON session_status_history(session_id);
CREATE INDEX IF NOT EXISTS idx_drafts_session ON session_drafts(session_id);
CREATE INDEX IF NOT EXISTS idx_drafts_expires ON session_drafts(expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_state ON sessions(state);
CREATE INDEX IF NOT EXISTS idx_sessions_parent ON sessions(parent_session_id);
