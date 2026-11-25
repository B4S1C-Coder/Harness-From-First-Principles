import logging
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
from confluent_kafka import Producer
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("commons.api")
TOPIC = "app-logs"


class KafkaHandler(logging.Handler):
    def __init__(self, producer: Producer) -> None:
        super().__init__()
        self.producer = producer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.producer.poll(0)
            self.producer.produce(TOPIC, value=self.format(record).encode())
        except (BufferError, RuntimeError):
            self.handleError(record)


def database() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    with database() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                author text NOT NULL,
                body text NOT NULL,
                likes integer NOT NULL DEFAULT 0,
                created_at timestamptz NOT NULL DEFAULT now()
            )
        """)
    producer = Producer({"bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"]})
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"
    )
    formatter.converter = time.gmtime
    logging.addLevelName(logging.WARNING, "WARN")
    handlers = [KafkaHandler(producer), logging.StreamHandler()]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in handlers:
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    try:
        logger.info("Feed service ready")
        yield
    finally:
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        producer.flush(5)


app = FastAPI(title="Commons", lifespan=lifespan)


@app.middleware("http")
async def access_log(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request.state.request_id = uuid4().hex[:12]
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        logger.info(
            "request=%s %s %r status=%s",
            request.state.request_id,
            request.method,
            request.url.path,
            response.status_code,
        )
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> Response:
    for error in exc.errors():
        logger.warning(
            "request=%s path=%r route=%s field=%s reason=%s",
            request.state.request_id,
            request.url.path,
            request.scope["route"].path,
            ".".join(map(str, error["loc"])),
            error["msg"],
        )
    return await request_validation_exception_handler(request, exc)


class Draft(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    author: str = Field(min_length=1, max_length=32)
    body: str = Field(min_length=1, max_length=280)


@app.get("/api/posts")
def feed() -> list[dict]:
    with database() as conn:
        return conn.execute("SELECT * FROM posts ORDER BY id DESC LIMIT 50").fetchall()


@app.post("/api/posts", status_code=201)
def publish(draft: Draft) -> dict:
    with database() as conn:
        return conn.execute(
            "INSERT INTO posts (author, body) VALUES (%s, %s) RETURNING *",
            (draft.author, draft.body),
        ).fetchone()


@app.get("/api/posts/{post_id}")
def detail(post_id: int) -> dict:
    with database() as conn:
        post = conn.execute("SELECT * FROM posts WHERE id = %s", (post_id,)).fetchone()
    if post is None:
        raise HTTPException(404, "Post not found")
    return post


@app.get("/api/posts/popular")
def popular() -> list[dict]:
    with database() as conn:
        return conn.execute("SELECT * FROM posts ORDER BY likes DESC, id DESC LIMIT 50").fetchall()


@app.post("/api/posts/{post_id}/likes")
def like(post_id: int) -> dict:
    with database() as conn:
        post = conn.execute(
            "UPDATE posts SET likes = likes + 1 WHERE id = %s RETURNING *", (post_id,)
        ).fetchone()
    if post is None:
        raise HTTPException(404, "Post not found")
    return post


app.mount("/", StaticFiles(directory=Path(__file__).parent / "frontend/dist", html=True))
