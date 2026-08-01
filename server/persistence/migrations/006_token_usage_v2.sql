CREATE TABLE IF NOT EXISTS pricing (
    model_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    input_1m REAL NOT NULL DEFAULT 0.0,
    output_1m REAL NOT NULL DEFAULT 0.0,
    cache_read_1m REAL NOT NULL DEFAULT 0.0,
    cache_creation_1m REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL
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

CREATE TABLE IF NOT EXISTS context_degradation (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    step_index INTEGER NOT NULL DEFAULT 0,
    before_tokens INTEGER NOT NULL DEFAULT 0,
    after_tokens INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

ALTER TABLE token_usage ADD COLUMN cost_usd REAL NOT NULL DEFAULT 0.0;
ALTER TABLE token_usage ADD COLUMN input_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE token_usage ADD COLUMN output_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE token_usage ADD COLUMN cache_read_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE token_usage ADD COLUMN cache_creation_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE token_usage ADD COLUMN step_index INTEGER NOT NULL DEFAULT -1;

CREATE INDEX IF NOT EXISTS idx_token_usage_created ON token_usage(created_at);
CREATE INDEX IF NOT EXISTS idx_token_usage_step ON token_usage(session_id, step_index);
CREATE INDEX IF NOT EXISTS idx_budget_session ON budget_settings(session_id);
CREATE INDEX IF NOT EXISTS idx_budget_events_session ON budget_events(session_id);
CREATE INDEX IF NOT EXISTS idx_context_degradation_session ON context_degradation(session_id);
CREATE INDEX IF NOT EXISTS idx_pricing_model ON pricing(provider, model_id);
