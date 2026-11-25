"""Run against the Compose app with the command in README.md."""

import json
import os
import re
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from confluent_kafka import Consumer


def api(path: str, payload: dict | None = None) -> dict | list:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        "http://localhost:8000/api/posts" + path,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=5) as response:
        return json.load(response)


class SmokeCheck(unittest.TestCase):
    def test_initialize_empty_and_existing_feed(self) -> None:
        from main import database, initialize_posts

        with database() as conn:
            conn.execute("CREATE TEMP TABLE posts (LIKE public.posts INCLUDING ALL)")
            initialize_posts(conn)
            seeded = conn.execute("SELECT * FROM posts ORDER BY id").fetchall()
            self.assertEqual(len(seeded), 3)
            initialize_posts(conn)
            self.assertEqual(conn.execute("SELECT * FROM posts ORDER BY id").fetchall(), seeded)

            conn.execute("DELETE FROM posts")
            conn.execute("INSERT INTO posts (author, body) VALUES ('Reader', 'My first post')")
            existing = conn.execute("SELECT * FROM posts").fetchall()
            initialize_posts(conn)
            self.assertEqual(conn.execute("SELECT * FROM posts").fetchall(), existing)

    def test_post_feed_and_like(self) -> None:
        post = api("", {"author": "Smoke check", "body": uuid4().hex})
        self.assertEqual(api(f"/{post['id']}"), post)
        self.assertIn(post, api(""))
        self.assertEqual(api(f"/{post['id']}/likes", {})["likes"], 1)

    def test_seeded_incident_is_logged(self) -> None:
        with self.assertRaises(HTTPError) as caught:
            api("/popular")
        self.assertEqual(caught.exception.code, 422)
        request_id = caught.exception.headers["X-Request-ID"]
        pattern = re.compile(
            r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} WARN \[[^\]]+\] commons\.api: "
            + f"request={re.escape(request_id)} "
            + r"path='/api/posts/popular' route=/api/posts/\{post_id\} field=path\.post_id"
        )
        consumer = Consumer(
            {
                "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"],
                "group.id": f"smoke-{uuid4().hex}",
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        try:
            consumer.subscribe(["app-logs"])
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                record = consumer.poll(1)
                if record and not record.error() and pattern.search(record.value().decode()):
                    return
            self.fail("Kafka did not receive the matching route validation warning")
        finally:
            consumer.close()


if __name__ == "__main__":
    unittest.main()
