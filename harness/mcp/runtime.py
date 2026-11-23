import json
import re
import time
from types import TracebackType
from typing import Any, Self

from harness import exceptions as err
from harness.logger import ApplicationLogger
from harness.tools import ExternalTool
from .client import StdioClient, VERSION
from .config import ServerConfig
from .http_client import HTTPClient

Client = StdioClient | HTTPClient
SUPPORTED_VERSIONS = (VERSION, "2025-06-18", "2025-03-26")


def _alias(server: str, tool: str) -> str:
    server, tool = (re.sub(r"[^A-Za-z0-9_-]", "_", s) for s in (server, tool))
    server = server[: max(31, 62 - len(tool))]
    return server + "__" + tool[: 62 - len(server)]


class RemoteTool(ExternalTool):
    def __init__(self, client: Client, spec: dict) -> None:
        self.client = client
        self.remote_name = spec["name"]
        self.name = _alias(client.name, self.remote_name)
        description = spec.get("description", "")
        if not isinstance(description, str):
            raise err.UnexpectedResponseError(client.name, "Invalid tool description.")
        self.description = description[:256]
        self.parameters = spec.get("inputSchema", {"type": "object", "properties": {}})

    def _bounded(self, text: str, failed: bool) -> dict:
        def envelope(n: int) -> dict:
            clipped = n < len(text)
            if failed:
                return {
                    "success": False,
                    "error": text[:n] + (" [truncated=true]" if clipped else ""),
                }
            return {"success": True, "data": {"text": text[:n], "truncated": clipped}}

        limit = self.client.config.max_result_bytes
        low, high = 0, min(len(text), limit)
        if (
            len(text) <= limit
            and len(json.dumps(envelope(len(text)), ensure_ascii=False).encode()) <= limit
        ):
            low = high = len(text)
        while low < high:
            mid = (low + high + 1) // 2
            if len(json.dumps(envelope(mid), ensure_ascii=False).encode()) <= limit:
                low = mid
            else:
                high = mid - 1
        result = envelope(low)
        if failed:
            raise err.ToolExecutionError(result["error"])
        return result["data"]

    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self.client.request(
                "tools/call", {"name": self.remote_name, "arguments": args}
            )
        except err.ToolExecutionError as exc:
            return self._bounded(exc.message, True)
        blocks = result.get("content")
        if not isinstance(blocks, list) or not all(isinstance(b, dict) for b in blocks):
            raise err.UnexpectedResponseError(self.client.name)
        parts = []
        for block in blocks:
            resource = block.get("resource")
            if block.get("type") == "text":
                parts.append(block.get("text"))
            elif (
                block.get("type") == "resource"
                and isinstance(resource, dict)
                and isinstance(resource.get("text"), str)
            ):
                parts.append(resource["text"])
            else:
                parts.append("[non-text content]")
        if not all(isinstance(p, str) for p in parts):
            raise err.UnexpectedResponseError(self.client.name)
        return self._bounded("\n".join(parts), result.get("isError", False))


class MCPRuntime:
    def __init__(self, config: dict[str, ServerConfig], logger: ApplicationLogger) -> None:
        self.config = config
        self.logger = logger
        self.clients: list[Client] = []
        self.tools: list[RemoteTool] = []

    def __enter__(self) -> Self:
        client = None
        aliases: dict[str, tuple[str, str]] = {}
        try:
            for name, config in self.config.items():
                client = None
                client = (
                    HTTPClient(name, config)
                    if config.url
                    else StdioClient(name, config, self.logger)
                )
                self.clients.append(client)
                deadline = time.monotonic() + config.timeout_seconds
                init = client.request(
                    "initialize",
                    {
                        "protocolVersion": VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "multi-agent-harness", "version": "0.1.0"},
                    },
                    deadline,
                )
                capabilities = init.get("capabilities")
                version = init.get("protocolVersion")
                if version not in SUPPORTED_VERSIONS:
                    raise err.UnexpectedResponseError(
                        name, f"Unsupported MCP revision {version!r}."
                    )
                if not isinstance(capabilities, dict) or not isinstance(
                    capabilities.get("tools"), dict
                ):
                    raise err.UnexpectedResponseError(
                        name, "Incompatible protocol or capabilities."
                    )
                client.initialized(version, deadline)
                available = set()
                kept = []
                cursors = set()
                params = {}
                while True:
                    if time.monotonic() >= deadline:
                        raise err.TimeoutError(name)
                    page = client.request("tools/list", params, deadline)
                    if not isinstance(page.get("tools"), list):
                        raise err.UnexpectedResponseError(name)
                    for spec in page["tools"]:
                        if not isinstance(spec, dict) or not isinstance(spec.get("name"), str):
                            raise err.UnexpectedResponseError(name)
                        raw = spec["name"]
                        available.add(raw)
                        if raw not in config.allowlist:
                            continue
                        tool = RemoteTool(client, spec)
                        origin = (name, raw)
                        if tool.name in aliases:
                            raise err.ConfigurationError(
                                f"Alias {tool.name} shared by {aliases[tool.name]} and {origin}"
                            )
                        aliases[tool.name] = origin
                        kept.append(tool)
                    cursor = page.get("nextCursor")
                    if cursor is None:
                        break
                    if not isinstance(cursor, str) or cursor in cursors:
                        raise err.UnexpectedResponseError(name, "Invalid pagination cursor.")
                    cursors.add(cursor)
                    params = {"cursor": cursor}
                missing = set(config.allowlist) - available
                if missing:
                    raise err.ConfigurationError(
                        f"{name}: missing {sorted(missing)}; available {sorted(available)}"
                    )
                self.tools.extend(kept)
                size = len(
                    json.dumps([t.instance_definition() for t in kept], ensure_ascii=False).encode()
                )
                self.logger.info(
                    "%s: kept %d MCP tools (%d definition bytes)", name, len(kept), size
                )
            return self
        except err.ApplicationException as exc:
            self.close()
            if isinstance(client, StdioClient):
                client.add_diagnostic(exc)
            raise
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        while self.clients:
            self.clients.pop().close()
        self.tools.clear()

    def __exit__(
        self, typ: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.close()
