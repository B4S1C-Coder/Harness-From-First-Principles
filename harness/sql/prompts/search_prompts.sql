SELECT id, name, description, created_at
FROM prompts
WHERE name LIKE ? OR description LIKE ? 
ORDER BY name;