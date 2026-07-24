-- Migration 004: Add tool_permissions table for persistent tool approval

CREATE TABLE IF NOT EXISTS tool_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    pattern TEXT NOT NULL DEFAULT '*',
    approved INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(tool_name, pattern)
);

CREATE INDEX IF NOT EXISTS idx_tool_permissions_name ON tool_permissions(tool_name);
