CREATE TABLE IF NOT EXISTS assistant_policy_templates (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    settings    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
