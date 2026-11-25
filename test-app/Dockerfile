FROM node:24.22.0-alpine AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY frontend/index.html frontend/src.jsx frontend/style.css ./
RUN pnpm build

FROM ghcr.io/astral-sh/uv:0.9.26 AS uv
FROM python:3.12-slim
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-cache
COPY main.py ./
COPY --from=frontend /ui/dist ./frontend/dist
CMD [".venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
