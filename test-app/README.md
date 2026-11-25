# Commons

From the repository root, start the stack with `docker compose -f infra/docker-compose.yaml up --build -d`. Open http://localhost:8000 for the feed or http://localhost:8000/docs for the REST API. Postgres and Kafka use temporary storage that clears when their containers stop.

## Seeded bug in the Popular feed

Select **Popular** in the UI, even with an empty feed. The request to `GET /api/posts/popular` returns HTTP 422. Use the request ID shown in the UI to find the matching `WARN` record in Kafka. It contains `path='/api/posts/popular' route=/api/posts/{post_id} field=path.post_id`.

```sh
docker compose -f infra/docker-compose.yaml exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka:29092 --topic app-logs --from-beginning
```

FastAPI matches routes in registration order. In [main.py](main.py), the dynamic route `/api/posts/{post_id}` is registered first. It matches `popular` as the post ID, then integer validation fails before the Popular feed handler runs.

To fix the bug, move the `popular()` handler and its decorator above the `detail()` handler and its decorator. After rebuilding the app, `GET /api/posts/popular` should return HTTP 200 with posts ordered by likes.

## Integration checks

Run the integration checks against a running stack and tear it down afterward. The checks create a post and expect the seeded incident to be present.

```sh
docker compose -f infra/docker-compose.yaml exec -T app .venv/bin/python - < test-app/smoke_check.py
docker compose -f infra/docker-compose.yaml down -v
```

The Docker build installs locked dependencies and serves the bundled React frontend from FastAPI. For local editing, run `uv sync --locked` and `nvm use` inside `test-app`, then `pnpm install --frozen-lockfile` and `pnpm build` inside `frontend`.
