SELECT
    pv.id,
    p.name,
    pv.version,
    pv.template,
    pv.created_at,
    pv.change_note
FROM prompts AS p
JOIN prompt_versions AS pv ON pv.prompt_id = p.id
WHERE p.name = ?
ORDER BY pv.version DESC
LIMIT 1;