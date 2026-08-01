-- HP-9: FTS5 full-text search over sessions and messages.
-- FTS5 virtual tables kept in sync with `messages` and `sessions` via triggers.

CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
    content,
    session_id UNINDEXED,
    role UNINDEXED,
    created_at UNINDEXED
);

CREATE VIRTUAL TABLE IF NOT EXISTS session_fts USING fts5(
    title,
    session_id UNINDEXED,
    created_at UNINDEXED
);

CREATE TRIGGER IF NOT EXISTS message_fts_ai AFTER INSERT ON messages BEGIN
    INSERT INTO message_fts(rowid, content, session_id, role, created_at)
    VALUES (new.rowid, new.content, new.session_id, new.role, new.created_at);
END;

CREATE TRIGGER IF NOT EXISTS message_fts_ad AFTER DELETE ON messages BEGIN
    DELETE FROM message_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS message_fts_au AFTER UPDATE ON messages BEGIN
    DELETE FROM message_fts WHERE rowid = old.rowid;
    INSERT INTO message_fts(rowid, content, session_id, role, created_at)
    VALUES (new.rowid, new.content, new.session_id, new.role, new.created_at);
END;

CREATE TRIGGER IF NOT EXISTS session_fts_ai AFTER INSERT ON sessions BEGIN
    INSERT INTO session_fts(rowid, title, session_id, created_at)
    VALUES (new.rowid, new.title, new.id, new.created_at);
END;

CREATE TRIGGER IF NOT EXISTS session_fts_ad AFTER DELETE ON sessions BEGIN
    DELETE FROM session_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS session_fts_au AFTER UPDATE ON sessions BEGIN
    DELETE FROM session_fts WHERE rowid = old.rowid;
    INSERT INTO session_fts(rowid, title, session_id, created_at)
    VALUES (new.rowid, new.title, new.id, new.created_at);
END;

-- Backfill for data that already exists in the source tables
INSERT INTO message_fts(rowid, content, session_id, role, created_at)
SELECT rowid, content, session_id, role, created_at FROM messages;

INSERT INTO session_fts(rowid, title, session_id, created_at)
SELECT rowid, title, id, created_at FROM sessions;
