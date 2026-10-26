INSERT INTO prompt_versions (
    prompt_id,
    version,
    template,
    change_note
)
VALUES (?, ?, ?, ?)
RETURNING id;