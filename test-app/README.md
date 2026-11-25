# Commons

From the repository root, start the stack with `docker compose -f infra/docker-compose.yaml up --build -d`. Open http://localhost:8000 for the feed or http://localhost:8000/docs for the REST API. Postgres and Kafka use temporary storage that clears when their containers stop.

Publish a post, like it, then select **Popular** to trigger the seeded incident. The UI shows a request ID you can match against the UTC records in Kafka.

```sh
docker compose -f infra/docker-compose.yaml exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka:29092 --topic app-logs --from-beginning
```

Run the integration checks against a running stack and tear it down afterward. The checks create a post and expect the seeded incident to be present.

```sh
docker compose -f infra/docker-compose.yaml exec -T app .venv/bin/python - < test-app/smoke_check.py
docker compose -f infra/docker-compose.yaml down -v
```

The Docker build installs locked dependencies and serves the bundled React frontend from FastAPI. For local editing, run `uv sync --locked` and `nvm use` inside `test-app`, then `pnpm install --frozen-lockfile` and `pnpm build` inside `frontend`.
