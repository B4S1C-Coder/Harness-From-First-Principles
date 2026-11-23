import json
import os
import subprocess
import threading
import time
from queue import Queue, Full
from typing import Any

from harness import exceptions as err
from .config import ServerConfig

VERSION = "2025-11-25"
FRAME_LIMIT = 8 * 1024 * 1024


class StdioClient:
    """One synchronous caller, with independent pipe workers for replies and pings."""

    def __init__(self, name: str, config: ServerConfig) -> None:
        self.name = name
        self.config = config
        env = {
            k: os.environ[k] for k in ("PATH", "SystemRoot", "HOME", "TMPDIR") if k in os.environ
        }
        try:
            self.process = subprocess.Popen(
                [config.command, *config.args],
                env=env | config.env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        except (OSError, ValueError) as exc:
            raise err.ConnectionError(name) from exc
        self.condition = threading.Condition()
        self.outgoing: Queue[bytes | None] = Queue(32)
        self.serial = threading.Lock()
        self.closed = False
        self.failure: err.ApplicationException | None = None
        self.sequence = 0
        self.reply: dict | None = None
        self.workers = [threading.Thread(target=f, daemon=True) for f in (self._read, self._write)]
        for worker in self.workers:
            worker.start()

    def _fail(self, exc: err.ApplicationException) -> None:
        with self.condition:
            self.failure = self.failure or exc
            self.condition.notify_all()
        if not self.closed and self.process.poll() is None:
            self.process.kill()
        try:
            self.outgoing.put_nowait(None)
        except Full:
            pass

    def send(self, **message: Any) -> None:
        payload = json.dumps({"jsonrpc": "2.0", **message}, allow_nan=False).encode() + b"\n"
        try:
            self.outgoing.put_nowait(payload)
        except Full:
            exc = err.ExternalServiceError(f"{self.name}: outbound queue full")
            self._fail(exc)
            raise exc from None

    def _write(self) -> None:
        pipe = self.process.stdin
        assert pipe is not None
        try:
            with pipe:
                while not self.failure and (data := self.outgoing.get()) is not None:
                    view = memoryview(data)
                    while view:
                        view = view[pipe.write(view) :]
        except OSError:
            self._fail(err.ConnectionError(self.name))

    def _read(self) -> None:
        import io

        assert self.process.stdout is not None
        try:
            with io.BufferedReader(self.process.stdout) as pipe:
                while line := pipe.readline(FRAME_LIMIT + 1):
                    if len(line) > FRAME_LIMIT or not line.endswith(b"\n"):
                        break
                    msg = json.loads(line)
                    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
                        break
                    if "method" in msg:
                        if "id" in msg:
                            result = (
                                {"result": {}}
                                if msg["method"] == "ping"
                                else {"error": {"code": -32601, "message": "Method not found"}}
                            )
                            self.send(id=msg["id"], **result)
                    else:
                        with self.condition:
                            if type(msg.get("id")) is not int or msg["id"] != self.sequence:
                                break
                            self.reply = msg
                            self.condition.notify_all()
                else:
                    self._fail(err.ConnectionError(self.name))
                    return
        except (ValueError, OSError, RecursionError, err.ApplicationException):
            pass
        self._fail(err.UnexpectedResponseError(self.name, "Invalid MCP frame."))

    def request(self, method: str, params: dict, deadline: float | None = None) -> dict:
        deadline = (
            deadline if deadline is not None else time.monotonic() + self.config.timeout_seconds
        )
        if not self.serial.acquire(timeout=max(0, deadline - time.monotonic())):
            raise err.TimeoutError(self.name)
        try:
            with self.condition:
                if self.failure:
                    raise self.failure
                self.sequence += 1
                self.reply = None
                self.send(id=self.sequence, method=method, params=params)
                while self.reply is None and not self.failure:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self._fail(err.TimeoutError(self.name))
                        break
                    self.condition.wait(remaining)
                if self.reply is None:
                    assert self.failure
                    raise self.failure
                if isinstance(self.reply.get("error"), dict):
                    raise err.ToolExecutionError(
                        str(self.reply["error"].get("message", "RPC error"))
                    )
                if not isinstance(self.reply.get("result"), dict):
                    raise err.UnexpectedResponseError(self.name)
                return self.reply["result"]
        finally:
            self.serial.release()

    def close(self) -> None:
        with self.condition:
            if self.closed:
                return
            self.closed = True
            self.failure = self.failure or err.ConnectionError(self.name)
            self.condition.notify_all()
            try:
                self.outgoing.put_nowait(None)
            except Full:
                pass
        try:
            self.process.wait(timeout=0.25)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)
        for worker in self.workers:
            worker.join(timeout=0.5)
