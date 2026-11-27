# Commons RCA agent

From the repository root, register the three RCA prompts, start Commons, and launch the interactive agent.

```sh
uv run python -m rca.prompts
docker compose -f infra/docker-compose.yaml up -d
uv run python -m rca
```

Supply `MODEL_URL`, `API_KEY`, `GITHUB_TOKEN`, and `CONTEXT7_API_KEY` through the environment or root dotenv configuration. Reproduce the incident and ask “Why did the Popular feed fail?” Include the request ID when available. Use `exit` to quit.

Registration reads the Markdown drafts in `rca/prompts/` and adds missing families to `examples/data/prompts.db`. The CLI loads the registered versions of `rca.master.system`, `rca.logs.system`, and `rca.research.system`. Re-running registration preserves existing versions.

## Configuration

All three agents use an 8,000-token context budget. The master delegates focused questions. Each specialist receives its own history, including bounded excerpts from recent handoffs, and returns a short finding.

| Environment variable | Default |
|---|---|
| RCA_MASTER_MODEL, RCA_LOG_MODEL | openai/gpt-oss-120b |
| RCA_RESEARCH_MODEL | openai/gpt-oss-20b |
| RCA_MASTER_MAX_TOOL_TURNS, RCA_LOG_MAX_TOOL_TURNS, RCA_RESEARCH_MAX_TOOL_TURNS | 6 each |
| RCA_FINDING_BYTES | 1200 UTF-8 bytes per finding, configurable from 1 to 1800 |
| RCA_MEMORY_SIZE | 4 successful handoffs per specialist, 0 disables memory |
| KAFKA_BOOTSTRAP_SERVERS | localhost:9092 |
| KAFKA_LOG_TOPIC | app-logs |
| KAFKA_OFFSETS_PER_PARTITION | 1000 |

Each log delegation opens a fresh Kafka snapshot. The investigator starts with a digest, signatures, timeline and nearby rows, then uses focused searches to fill evidence gaps. The five tools leave room for evidence and subsequent calls within the free-tier budget.

## Citing a finding

Use the exact request ID and timestamp as the primary reference, for example `request=8ac1f4d2` at `2026-11-25 18:10:02,137`. Include a short excerpt if the ID is absent or multiple records match. A secondary reference such as `app-logs[0]@40:3` identifies the third ingested record in that partition’s snapshot starting at offset 40. Its line number is snapshot-local. In a later delegation, search by request ID and timestamp while the record is still in the window.
