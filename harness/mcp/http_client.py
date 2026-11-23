"""Synchronous Streamable HTTP with an absolute caller deadline."""

import http.client as http
import json
import socket
import threading
import time
from concurrent.futures import Future
from itertools import count
from typing import Any
from urllib.parse import urlsplit

from harness import exceptions as err
from .client import FRAME_LIMIT
from .config import ServerConfig

STREAM_LIMIT = 16 * 1024 * 1024


class HTTPClient:
    def __init__(self, name: str, config: ServerConfig) -> None:
        self.name = name
        self.config = config
        assert config.url is not None
        self.endpoint = urlsplit(config.url)
        self.path = self.endpoint.path or "/"
        if self.endpoint.query:
            self.path += "?" + self.endpoint.query
        self.ids = count(1)
        self.version: str | None = None
        self.session: str | None = None
        self.dead = False
        self.lock = threading.Lock()
        self.sockets: set[socket.socket] = set()

    def _abort(self) -> None:
        with self.lock:
            self.dead = True
            for sock in self.sockets:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise err.TimeoutError(self.name)
        if self.dead:
            raise err.ConnectionError(self.name)
        return remaining

    def _run(self, msg: dict | None, deadline: float) -> dict:
        future: Future[dict] = Future()

        def worker() -> None:
            try:
                future.set_result(self._exchange(msg, deadline))
            except Exception as exc:
                future.set_exception(exc)

        try:
            self._remaining(deadline)
            threading.Thread(target=worker, daemon=True).start()
            return future.result(max(0, deadline - time.monotonic()))
        except (TimeoutError, err.TimeoutError):
            self._abort()
            raise err.TimeoutError(self.name) from None
        except err.ApplicationException:
            raise
        except (OSError, http.HTTPException):
            raise err.ConnectionError(self.name) from None
        except (ValueError, RecursionError):
            raise err.UnexpectedResponseError(self.name, "Invalid HTTP response.") from None

    def request(self, method: str, params: dict, deadline: float | None = None) -> dict:
        return self._run(
            {"id": next(self.ids), "method": method, "params": params},
            deadline or time.monotonic() + self.config.timeout_seconds,
        )

    def initialized(self, version: str, deadline: float) -> None:
        self.version = version
        self._run({"method": "notifications/initialized"}, deadline)

    def _exchange(self, msg: dict | None, deadline: float) -> dict:
        cls = http.HTTPSConnection if self.endpoint.scheme == "https" else http.HTTPConnection
        conn = cls(self.endpoint.hostname, self.endpoint.port, timeout=self._remaining(deadline))
        headers = {
            **self.config.headers,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        if self.version:
            headers["MCP-Protocol-Version"] = self.version
        sock = None
        try:
            conn.connect()
            sock = conn.sock
            assert sock is not None
            with self.lock:
                sock.settimeout(self._remaining(deadline))
                self.sockets.add(sock)
            body = json.dumps({"jsonrpc": "2.0", **msg}).encode() if msg is not None else None
            conn.request("DELETE" if msg is None else "POST", self.path, body, headers)
            with conn.getresponse() as response:
                status = response.status
                if msg is None and status == 405:
                    return {}
                if status in (401, 403):
                    raise err.PermissionDenied(f"{self.name}: HTTP {status} authorization denied.")
                if status == 429:
                    raise err.RateLimitedError(self.name)
                if status == 404 and self.session:
                    self._abort()
                    raise err.ExternalServiceError(
                        f"{self.name}: MCP session expired; reopen runtime."
                    )
                if not 200 <= status < 300:
                    raise err.ExternalServiceError(f"{self.name}: HTTP {status}.")
                if msg is None:
                    return {}
                if "method" not in msg or "id" not in msg:
                    if status != 202 or response.read(1):
                        raise err.UnexpectedResponseError(self.name, "Expected empty HTTP 202.")
                    return {}
                if msg["method"] == "initialize":
                    session = response.getheader("Mcp-Session-Id")
                    if session is not None and (
                        not session or not all(33 <= ord(c) <= 126 for c in session)
                    ):
                        raise err.UnexpectedResponseError(self.name, "Invalid session ID.")
                    with self.lock:
                        self._remaining(deadline)
                        self.session = session
                media = response.getheader("Content-Type", "").partition(";")[0].strip().lower()
                if media == "text/event-stream":
                    return self._stream(response, msg["id"], deadline)
                if media != "application/json":
                    raise err.UnexpectedResponseError(self.name, "Expected JSON or SSE.")
                raw = response.read(FRAME_LIMIT + 1)
                if len(raw) > FRAME_LIMIT:
                    raise err.UnexpectedResponseError(self.name, "Message too large.")
                return self._result(json.loads(raw.decode()), msg["id"])
        finally:
            with self.lock:
                self.sockets.discard(sock)
            conn.close()

    def _result(self, obj: Any, expected: int) -> dict:
        if (
            not isinstance(obj, dict)
            or obj.get("jsonrpc") != "2.0"
            or type(obj.get("id")) is not int
            or obj["id"] != expected
            or ("result" in obj) == ("error" in obj)
            or "method" in obj
        ):
            raise err.UnexpectedResponseError(self.name, "Invalid JSON-RPC reply.")
        if isinstance(obj.get("error"), dict) and isinstance(obj["error"].get("message"), str):
            raise err.ToolExecutionError(obj["error"]["message"])
        if not isinstance(obj.get("result"), dict):
            raise err.UnexpectedResponseError(self.name)
        return obj["result"]

    def _stream(self, response: http.HTTPResponse, expected: int, deadline: float) -> dict:
        total = 0
        data = bytearray()
        while line := response.readline(FRAME_LIMIT + 1):
            self._remaining(deadline)
            total += len(line)
            if total > STREAM_LIMIT or len(line) > FRAME_LIMIT:
                raise err.UnexpectedResponseError(self.name, "SSE size limit exceeded.")
            line = line.rstrip(b"\r\n")
            if line.startswith(b"data:"):
                value = line[5:].removeprefix(b" ")
                data.extend(value + b"\n")
                if len(data) > FRAME_LIMIT:
                    raise err.UnexpectedResponseError(self.name, "Message too large.")
            elif not line and data:
                payload = data.strip()
                data.clear()
                if not payload:
                    continue
                obj = json.loads(payload.decode())
                if not isinstance(obj, dict) or obj.get("jsonrpc") != "2.0":
                    raise err.UnexpectedResponseError(self.name)
                if "method" not in obj:
                    return self._result(obj, expected)
                if "id" in obj:
                    reply = (
                        {"result": {}}
                        if obj["method"] == "ping"
                        else {"error": {"code": -32601, "message": "Method not found"}}
                    )
                    self._exchange({"id": obj["id"], **reply}, deadline)
        raise err.UnexpectedResponseError(self.name, "SSE ended before the reply.")

    def close(self) -> None:
        try:
            if self.session and not self.dead:
                self._run(None, time.monotonic() + min(1, self.config.timeout_seconds))
        except err.ApplicationException:
            pass
        finally:
            self._abort()
