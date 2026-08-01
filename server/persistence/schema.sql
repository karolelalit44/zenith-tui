-- Core Schema for Zenith Session Management
-- SQLite as single source of truth for all session data

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New Session',
    mode TEXT NOT NULL DEFAULT 'build',
    state TEXT NOT NULL DEFAULT 'created',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    workspace_root TEXT NOT NULL DEFAULT '.',
    is_active INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL DEFAULT '{}',

    -- Extended state
    parent_session_id TEXT,
    plan_output TEXT NOT NULL DEFAULT '',
    plan_approved_at TEXT,
    message_count INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    total_cost REAL NOT NULL DEFAULT 0.0,
    model TEXT,
    provider TEXT,
    agent_state TEXT NOT NULL DEFAULT 'idle',

    -- Context tracking
    context_used INTEGER NOT NULL DEFAULT 0,
    context_window INTEGER NOT NULL DEFAULT 0,
    context_percent REAL NOT NULL DEFAULT 0.0,

    -- Error tracking
    error_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,

    -- Export tracking
    export_format TEXT,
    exported_at TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    events_json TEXT NOT NULL DEFAULT '[]',
    token_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    api_key TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    max_tokens INTEGER NOT NULL DEFAULT 4096,
    temperature REAL NOT NULL DEFAULT 0.7,
    is_active INTEGER NOT NULL DEFAULT 0,
    swatch_json TEXT NOT NULL DEFAULT '[]',
    adapter_type TEXT NOT NULL DEFAULT 'openai_compat',
    capabilities_json TEXT NOT NULL DEFAULT '{}',
    api_key_prefix TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_models (
    id TEXT NOT NULL,
    provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    context_window INTEGER NOT NULL DEFAULT 128000,
    description TEXT NOT NULL DEFAULT '',
    is_default INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (provider_id, id)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS token_usage (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    context_window INTEGER NOT NULL DEFAULT 0,
    percent REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    cost_usd REAL NOT NULL DEFAULT 0.0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    step_index INTEGER NOT NULL DEFAULT -1,
    estimated INTEGER NOT NULL DEFAULT 0,
    is_retry INTEGER NOT NULL DEFAULT 0,
    retry_of TEXT,
    duration_ms INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS context_degradation (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    step_index INTEGER NOT NULL,
    before_tokens INTEGER NOT NULL,
    after_tokens INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pricing (
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    input_1m REAL NOT NULL DEFAULT 0.0,
    output_1m REAL NOT NULL DEFAULT 0.0,
    cache_read_1m REAL NOT NULL DEFAULT 0.0,
    cache_creation_1m REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (provider, model_id)
);

CREATE TABLE IF NOT EXISTS budget_settings (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    max_session_cost REAL NOT NULL DEFAULT 0.0,
    max_daily_cost REAL NOT NULL DEFAULT 0.0,
    max_monthly_cost REAL NOT NULL DEFAULT 0.0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budget_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    current_cost REAL NOT NULL DEFAULT 0.0,
    budget_limit REAL NOT NULL DEFAULT 0.0,
    message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

-- New tables for session management

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

-- HP-8: persistent permission decisions (grant/deny rules that survive restarts)
CREATE TABLE IF NOT EXISTS permissions (
    id TEXT PRIMARY KEY,
    tool_name TEXT NOT NULL,
    decision TEXT NOT NULL,
    session_id TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_permissions_tool ON permissions(tool_name);
CREATE INDEX IF NOT EXISTS idx_permissions_session ON permissions(session_id);

-- Indexes

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active);
CREATE INDEX IF NOT EXISTS idx_sessions_state ON sessions(state);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at);
CREATE INDEX IF NOT EXISTS idx_sessions_parent ON sessions(parent_session_id);
CREATE INDEX IF NOT EXISTS idx_providers_active ON providers(is_active);
CREATE INDEX IF NOT EXISTS idx_provider_models_pid ON provider_models(provider_id);

CREATE INDEX IF NOT EXISTS idx_token_usage_session ON token_usage(session_id);
CREATE INDEX IF NOT EXISTS idx_token_usage_step ON token_usage(session_id, step_index);

CREATE INDEX IF NOT EXISTS idx_checkpoints_session ON session_checkpoints(session_id);
CREATE INDEX IF NOT EXISTS idx_sync_events_session_seq ON sync_events(session_id, sequence);
CREATE INDEX IF NOT EXISTS idx_status_history_session ON session_status_history(session_id);

CREATE INDEX IF NOT EXISTS idx_drafts_session ON session_drafts(session_id);
CREATE INDEX IF NOT EXISTS idx_drafts_expires ON session_drafts(expires_at);
