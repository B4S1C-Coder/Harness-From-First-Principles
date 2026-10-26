SELECT
    pv.id,
    p.name,
    pv.version,
    pv.template,
    pv.created_at,
    pv.change_note
FROM prompt_versions AS pv
JOIN prompts AS p ON p.id = pv.prompt_id
WHERE p.name = ? AND pv.version = ?;