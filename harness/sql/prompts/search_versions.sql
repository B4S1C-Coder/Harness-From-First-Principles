SELECT
    p.name,
    pv.version,
    pv.template,
    pv.created_at,
    pv.change_note
FROM prompt_versions AS pv
JOIN prompts AS p ON p.id = pv.prompt_id
WHERE pv.template LIKE ?
ORDER BY p.name, pv.version DESC;