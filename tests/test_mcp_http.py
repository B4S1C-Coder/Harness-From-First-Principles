from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from typing import Any
import pytest
from harness import exceptions as err
from harness.logger import ApplicationLogger
from harness.mcp import MCPRuntime, ServerConfig
from harness.mcp import http_client
from harness.tools import ToolExecutor


@contextmanager
def peer(mode: str, version: str = "2025-06-18", location: str = "") -> Iterator[tuple[str, list]]:
    seen = []
    ping = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_DELETE(self) -> None:
            seen.append(("DELETE", self.headers))
            self.send_response(405)
            self.end_headers()

        def do_POST(self) -> None:
            msg = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            method = msg.get("method", "reply")
            seen.append((method, self.headers))
            if method == "initialize":
                result = {"protocolVersion": version, "capabilities": {"tools": {}}}
            elif method in ("notifications/initialized", "reply"):
                self.send_response(200 if mode == "bad-ack" else 202)
                self.end_headers()
                if method == "reply" and msg.get("result") == {} and msg["id"] == "p":
                    ping.set()
                return
            elif method == "tools/list":
                result = {"tools": [{"name": "read"}]}
            else:
                result = {"content": [{"type": "resource", "resource": {"text": "embedded"}}]}
            call = method == "tools/call"
            if call and mode.isdigit():
                self.send_response(int(mode))
                if location:
                    self.send_header("Location", location)
                self.end_headers()
                self.wfile.write(b"secret-token")
                return
            self.send_response(200)
            stream = call and mode in ("sse", "bad-sse", "flood", "slow")
            self.send_header("Content-Type", "text/event-stream" if stream else "application/json")
            if method == "initialize":
                self.send_header("Mcp-Session-Id", "session")
            self.end_headers()
            doc = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"] if mode != "wrong" or not call else -1,
                    "result": result,
                }
            ).encode()
            try:
                if stream:
                    if mode == "slow":
                        for _ in range(40):
                            self.wfile.write(b":tick\n\n")
                            time.sleep(0.04)
                    if mode == "flood":
                        self.wfile.write(b":comment\n\n" * 100)
                    if mode == "bad-sse":
                        self.wfile.write(b"data: invalid\n\n")
                        return
                    self.wfile.write(b'data: {"jsonrpc":"2.0","id":"p","method":"ping"}\n\n')
                    if ping.wait(2):
                        self.wfile.write(b"data: " + doc + b"\n\n")
                else:
                    if call and mode == "large":
                        doc += b" " * 2000
                    self.wfile.write(b"?" if call and mode == "bad-json" else doc)
            except OSError:
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/mcp", seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def runtime(url: str, logger: ApplicationLogger) -> MCPRuntime:
    return MCPRuntime(
        {
            "r": ServerConfig(
                url=url,
                allowlist=["read"],
                timeout_seconds=0.5,
                headers={"Authorization": "Bearer secret-token"},
            )
        },
        logger,
    )


@pytest.mark.parametrize(("mode", "version"), [("json", "2025-03-26"), ("sse", "2025-06-18")])
def test_http(mode: str, version: str, app_logger: ApplicationLogger) -> None:
    with peer(mode, version) as (url, seen):
        with runtime(url, app_logger) as active:
            output = ToolExecutor(app_logger, active.tools).execute("r__read", {})
            assert json.loads(output)["data"]["text"] == "embedded"
        assert seen[-1][0] == "DELETE"
        for method, headers in seen:
            assert headers["Authorization"] == "Bearer secret-token"
            if method != "DELETE":
                assert headers["Content-Type"] == "application/json"
                assert headers["Accept"] == "application/json, text/event-stream"
            if method != "initialize":
                assert headers["Mcp-Session-Id"] == "session"
                assert headers["MCP-Protocol-Version"] == version


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("401", "401"),
        ("403", "403"),
        ("404", "expired"),
        ("429", "rate limits"),
        ("503", "503"),
        ("wrong", "unexpected"),
        ("bad-json", "unexpected"),
        ("bad-sse", "unexpected"),
        ("large", "large"),
        ("flood", "size"),
        ("slow", "timed out"),
    ],
)
def test_http_failure(
    mode: str, message: str, app_logger: ApplicationLogger, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(http_client, "FRAME_LIMIT", 1024)
    monkeypatch.setattr(http_client, "STREAM_LIMIT", 512)
    with peer(mode) as (url, _), runtime(url, app_logger) as active:
        start = time.monotonic()
        executor = ToolExecutor(app_logger, active.tools)
        output = json.loads(executor.execute("r__read", {}))
        assert message in output["error"] and "secret-token" not in output["error"]
        if mode in ("404", "slow"):
            assert time.monotonic() - start < 1
            assert active.clients[0].dead


def test_redirect(app_logger: ApplicationLogger) -> None:
    with peer("json") as (target, hits), peer("307", location=target) as (url, _):
        with runtime(url, app_logger) as active:
            with pytest.raises(err.ExternalServiceError, match="307"):
                active.tools[0].driver({})
        assert not hits


def test_https() -> None:
    with pytest.raises(err.ConfigurationError, match="HTTPS"):
        ServerConfig(url="http://localhost.example", allowlist=["read"])


def test_transport_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from harness.mcp import load_mcp_config

    path = tmp_path / "servers.json"
    config = {
        "url": "https://host.test",
        "allowlist": ["read"],
        "headers": {"Authorization": "Bearer ${TOKEN}"},
    }
    path.write_text(json.dumps({"servers": {"remote": config}}))
    monkeypatch.setenv("TOKEN", "secret-token")
    assert load_mcp_config(path)["remote"].headers["Authorization"] == "Bearer secret-token"
    for invalid in (
        {},
        {"command": "python", "url": "https://host.test"},
        {"command": "python", "headers": {"Authorization": "a"}},
        {"url": "https://host.test", "args": ["arg"]},
    ):
        with pytest.raises(err.ConfigurationError):
            ServerConfig(allowlist=["read"], **invalid)


def test_notification_acknowledgement(app_logger: ApplicationLogger) -> None:
    with peer("bad-ack") as (url, _), pytest.raises(err.UnexpectedResponseError, match="202"):
        with runtime(url, app_logger):
            pass
