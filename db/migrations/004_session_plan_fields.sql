ALTER TABLE sessions ADD COLUMN parent_session_id TEXT REFERENCES sessions(id);
ALTER TABLE sessions ADD COLUMN state TEXT NOT NULL DEFAULT 'created';
ALTER TABLE sessions ADD COLUMN plan_output TEXT NOT NULL DEFAULT '';
ALTER TABLE sessions ADD COLUMN plan_approved_at TEXT;
