CREATE TABLE IF NOT EXISTS prompt_versions (
    id INTEGER PRIMARY KEY,
    prompt_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    template TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    change_note TEXT,

    UNIQUE (prompt_id, version),

    FOREIGN KEY (prompt_id) REFERENCES prompts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_prompt_versions_lookup ON prompt_versions(
    prompt_id, version DESC
);