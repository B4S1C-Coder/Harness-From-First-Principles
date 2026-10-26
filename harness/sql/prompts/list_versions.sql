SELECT version, created_at, change_note
FROM prompt_versions
WHERE prompt_id = ?
ORDER BY version DESC;