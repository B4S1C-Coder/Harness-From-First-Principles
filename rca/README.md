# Commons RCA agent

From the repository root, start Commons with `docker compose -f infra/docker-compose.yaml up -d`. Open the feed and reproduce the incident. Supply `MODEL_URL`, `API_KEY`, `GITHUB_TOKEN`, and `CONTEXT7_API_KEY` through the environment or the root dotenv configuration, then run `uv run python -m rca`. Ask “Why did the Popular feed fail?” or paste the request ID. Use `exit` to end the session.

The master and log investigator use `openai/gpt-oss-120b`. The `openai/gpt-oss-20b` researcher can read GitHub files, read and search issues and query Context7 library documentation. Only the master sees the user conversation. It passes a focused question to each specialist and receives a bounded report. Each specialist remembers its four latest successful question/report pairs in memory for the session.

Each log delegation snapshots the latest 1,000 offsets per partition on `localhost:9092`, topic `app-logs`. Override those defaults with `KAFKA_BOOTSTRAP_SERVERS` and `KAFKA_LOG_TOPIC`. A citation such as `app-logs[0]@40:3` refers to the third ingested record in partition 0’s snapshot starting at offset 40. The investigator queries the snapshot through the harness log tools. A subsequent delegation sees records published since the earlier call, subject to the same snapshot limit.
