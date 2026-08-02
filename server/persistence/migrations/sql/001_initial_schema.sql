-- 001: initial schema (baseline of the pre-Alembic schema)
--
-- One-time baseline reproducing the schema produced by the legacy schema.sql
-- plus numbered migrations 002-010, including the FTS5 virtual tables and their
-- sync triggers. Verified against a copy of data/zenith.db before being committed.
--
-- NOTE: this file is intentionally NOT idempotent (plain CREATE TABLE). A failed
-- run leaves partial DDL behind; reconcile manually, then re-run the migrate
-- command. Future schema changes go into higher-numbered files.

-- ---------------------------------------------------------------------------
-- Core session tables
-- ---------------------------------------------------------------------------

CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL DEFAULT 'New Session',
    mode            TEXT NOT NULL DEFAULT 'build',
    state           TEXT NOT NULL DEFAULT 'created',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    workspace_root  TEXT NOT NULL DEFAULT '.',
    is_active       INTEGER NOT NULL DEFAULT 1,
    metadata_json   TEXT NOT NULL DEFAULT '{}',
    parent_session_id TEXT,
    plan_output     TEXT NOT NULL DEFAULT '',
    plan_approved_at TEXT,
    message_count   INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER NOT NULL DEFAULT 0,
    total_cost      REAL NOT NULL DEFAULT 0.0,
    model           TEXT,
    provider        TEXT,
    agent_state     TEXT NOT NULL DEFAULT 'idle',
    context_used    INTEGER NOT NULL DEFAULT 0,
    context_window  INTEGER NOT NULL DEFAULT 0,
    context_percent REAL NOT NULL DEFAULT 0.0,
    error_count     INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    export_format   TEXT,
    exported_at     TEXT
);

CREATE INDEX idx_sessions_active ON sessions (is_active);
CREATE INDEX idx_sessions_state ON sessions (state);
CREATE INDEX idx_sessions_updated ON sessions (updated_at);
CREATE INDEX idx_sessions_parent ON sessions (parent_session_id);

CREATE TABLE messages (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    role         TEXT NOT NULL,
    content      TEXT NOT NULL DEFAULT '',
    events_json  TEXT NOT NULL DEFAULT '[]',
    token_count  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_messages_session ON messages (session_id);
CREATE INDEX idx_messages_created ON messages (created_at);

CREATE TABLE providers (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    api_key          TEXT NOT NULL DEFAULT '',
    model            TEXT NOT NULL DEFAULT '',
    base_url         TEXT NOT NULL DEFAULT '',
    max_tokens       INTEGER NOT NULL DEFAULT 4096,
    temperature      REAL NOT NULL DEFAULT 0.7,
    is_active        INTEGER NOT NULL DEFAULT 0,
    swatch_json      TEXT NOT NULL DEFAULT '[]',
    adapter_type     TEXT NOT NULL DEFAULT 'openai_compat',
    capabilities_json TEXT NOT NULL DEFAULT '{}',
    api_key_prefix   TEXT,
    updated_at       TEXT NOT NULL
);

CREATE INDEX idx_providers_active ON providers (is_active);

CREATE TABLE provider_models (
    id              TEXT NOT NULL,
    provider_id     TEXT NOT NULL REFERENCES providers (id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    context_window  INTEGER NOT NULL DEFAULT 128000,
    description     TEXT NOT NULL DEFAULT '',
    is_default      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (provider_id, id)
);

CREATE INDEX idx_provider_models_pid ON provider_models (provider_id);

CREATE TABLE app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Token usage / context / pricing / budget
-- ---------------------------------------------------------------------------

CREATE TABLE token_usage (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    provider            TEXT NOT NULL DEFAULT '',
    model               TEXT NOT NULL DEFAULT '',
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    completion_tokens   INTEGER NOT NULL DEFAULT 0,
    total_tokens        INTEGER NOT NULL DEFAULT 0,
    context_window      INTEGER NOT NULL DEFAULT 0,
    percent             REAL NOT NULL DEFAULT 0.0,
    created_at          TEXT NOT NULL,
    cost_usd            REAL NOT NULL DEFAULT 0.0,
    input_tokens        INTEGER NOT NULL DEFAULT 0,
    output_tokens       INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens   INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens  INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens    INTEGER NOT NULL DEFAULT 0,
    step_index          INTEGER NOT NULL DEFAULT -1,
    estimated           INTEGER NOT NULL DEFAULT 0,
    is_retry            INTEGER NOT NULL DEFAULT 0,
    retry_of            TEXT,
    duration_ms         INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_token_usage_session ON token_usage (session_id);
CREATE INDEX idx_token_usage_step ON token_usage (session_id, step_index);
CREATE INDEX idx_token_usage_model ON token_usage (provider, model);

CREATE TABLE context_degradation (
    id            TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    step_index    INTEGER NOT NULL,
    before_tokens INTEGER NOT NULL,
    after_tokens  INTEGER NOT NULL,
    reason        TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE pricing (
    model_id           TEXT NOT NULL,
    provider           TEXT NOT NULL,
    input_1m           REAL NOT NULL DEFAULT 0.0,
    output_1m          REAL NOT NULL DEFAULT 0.0,
    cache_read_1m      REAL NOT NULL DEFAULT 0.0,
    cache_creation_1m  REAL NOT NULL DEFAULT 0.0,
    updated_at         TEXT NOT NULL,
    PRIMARY KEY (provider, model_id)
);

CREATE TABLE budget_settings (
    id               TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    max_session_cost REAL NOT NULL DEFAULT 0.0,
    max_daily_cost   REAL NOT NULL DEFAULT 0.0,
    max_monthly_cost REAL NOT NULL DEFAULT 0.0,
    active           INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE budget_events (
    id            TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    event_type    TEXT NOT NULL,
    current_cost  REAL NOT NULL DEFAULT 0.0,
    budget_limit  REAL NOT NULL DEFAULT 0.0,
    message       TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Session management
-- ---------------------------------------------------------------------------

CREATE TABLE session_checkpoints (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    checkpoint_type TEXT NOT NULL DEFAULT 'automatic',
    step_index      INTEGER NOT NULL DEFAULT 0,
    snapshot_data   TEXT NOT NULL DEFAULT '{}',
    token_count     INTEGER NOT NULL DEFAULT 0,
    message_count   INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE INDEX idx_checkpoints_session ON session_checkpoints (session_id);

CREATE TABLE sync_events (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,
    event_data  TEXT NOT NULL DEFAULT '{}',
    sequence    INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX idx_sync_events_session_seq ON sync_events (session_id, sequence);

CREATE TABLE session_status_history (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    from_state  TEXT,
    to_state    TEXT NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE INDEX idx_status_history_session ON session_status_history (session_id);

CREATE TABLE session_drafts (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    prompt      TEXT NOT NULL DEFAULT '',
    context     TEXT NOT NULL DEFAULT '{}',
    expires_at  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX idx_drafts_session ON session_drafts (session_id);
CREATE INDEX idx_drafts_expires ON session_drafts (expires_at);

-- ---------------------------------------------------------------------------
-- Permissions
-- ---------------------------------------------------------------------------

CREATE TABLE permissions (
    id          TEXT PRIMARY KEY,
    tool_name   TEXT NOT NULL,
    decision    TEXT NOT NULL,
    session_id  TEXT,
    expires_at  TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX idx_permissions_tool ON permissions (tool_name);
CREATE INDEX idx_permissions_session ON permissions (session_id);

-- ---------------------------------------------------------------------------
-- FTS5 search indexes + sync triggers
-- ---------------------------------------------------------------------------

CREATE VIRTUAL TABLE message_fts USING fts5(
    content, session_id UNINDEXED, role UNINDEXED, created_at UNINDEXED
);

CREATE VIRTUAL TABLE session_fts USING fts5(
    title, session_id UNINDEXED, created_at UNINDEXED
);

CREATE TRIGGER message_fts_ai AFTER INSERT ON messages BEGIN
    INSERT INTO message_fts(rowid, content, session_id, role, created_at)
    VALUES (new.rowid, new.content, new.session_id, new.role, new.created_at);
END;

CREATE TRIGGER message_fts_ad AFTER DELETE ON messages BEGIN
    DELETE FROM message_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER message_fts_au AFTER UPDATE ON messages BEGIN
    DELETE FROM message_fts WHERE rowid = old.rowid;
    INSERT INTO message_fts(rowid, content, session_id, role, created_at)
    VALUES (new.rowid, new.content, new.session_id, new.role, new.created_at);
END;

CREATE TRIGGER session_fts_ai AFTER INSERT ON sessions BEGIN
    INSERT INTO session_fts(rowid, title, session_id, created_at)
    VALUES (new.rowid, new.title, new.id, new.created_at);
END;

CREATE TRIGGER session_fts_ad AFTER DELETE ON sessions BEGIN
    DELETE FROM session_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER session_fts_au AFTER UPDATE ON sessions BEGIN
    DELETE FROM session_fts WHERE rowid = old.rowid;
    INSERT INTO session_fts(rowid, title, session_id, created_at)
    VALUES (new.rowid, new.title, new.id, new.created_at);
END;
