-- HP-8: persistent permission decisions
-- Stores tool permission grants/denies that survive server restarts.

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
