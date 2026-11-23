import json
import math
import os
from pathlib import Path
from urllib.parse import urlsplit
import re
from dataclasses import dataclass, field

from harness.exceptions import ConfigurationError, EnvVarNotSetError


@dataclass(frozen=True)
class ServerConfig:
    command: str | None = None
    allowlist: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict, repr=False)
    timeout_seconds: float = 10
    max_result_bytes: int = 4096

    url: str | None = field(default=None, kw_only=True)
    headers: dict[str, str] = field(default_factory=dict, kw_only=True, repr=False)

    def __post_init__(self) -> None:
        if (self.command is None) == (self.url is None):
            raise ConfigurationError("Supply exactly one MCP command or URL.")
        if self.url is not None:
            if not isinstance(self.url, str) or self.args or self.env:
                raise ConfigurationError("Invalid HTTP server options.")
            try:
                endpoint = urlsplit(self.url)
                port = endpoint.port
            except ValueError:
                raise ConfigurationError("Invalid MCP URL.") from None
            if (
                not endpoint.hostname
                or port == 0
                or endpoint.username is not None
                or endpoint.fragment
                or any(ord(c) <= 32 for c in self.url)
                or not (
                    endpoint.scheme == "https"
                    or (
                        endpoint.scheme == "http"
                        and endpoint.hostname in ("localhost", "127.0.0.1")
                    )
                )
            ):
                raise ConfigurationError("MCP requires HTTPS except on localhost or 127.0.0.1.")
            reserved = {
                "host",
                "accept",
                "content-type",
                "content-length",
                "transfer-encoding",
                "mcp-session-id",
                "mcp-protocol-version",
                "connection",
                "accept-encoding",
            }
            if not isinstance(self.headers, dict) or any(
                not isinstance(k, str)
                or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", k)
                or k.lower() in reserved
                or not isinstance(v, str)
                or not all(32 <= ord(c) <= 126 for c in v)
                for k, v in self.headers.items()
            ):
                raise ConfigurationError("Invalid or reserved MCP HTTP header.")
        elif self.headers or not isinstance(self.command, str) or not self.command:
            raise ConfigurationError("Expected a server command.")
        for values in (self.args, self.allowlist):
            if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
                raise ConfigurationError("Expected a list of strings.")
        if not self.allowlist or not all(self.allowlist):
            raise ConfigurationError("Expected a nonempty allowlist.")
        if not isinstance(self.env, dict) or not all(isinstance(v, str) for v in self.env.values()):
            raise ConfigurationError("Expected string environment values.")
        if (
            type(self.timeout_seconds) not in (float, int)
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ConfigurationError("Expected a positive finite timeout.")
        if type(self.max_result_bytes) is not int or self.max_result_bytes < 64:
            raise ConfigurationError("Result limit must be at least 64 bytes.")


def _expand(match: re.Match[str]) -> str:
    name = match[1]
    if name not in os.environ:
        raise EnvVarNotSetError(name)
    return os.environ[name]


def load_mcp_config(path: str | Path) -> dict[str, ServerConfig]:
    def expand(value: object) -> object:
        if isinstance(value, str):
            return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", _expand, value)
        if isinstance(value, list):
            return [expand(v) for v in value]
        if isinstance(value, dict):
            return {k: expand(v) for k, v in value.items()}
        return value

    try:
        servers = json.loads(Path(path).read_text(encoding="utf-8"))["servers"]
        result = {}
        for name, config in servers.items():
            if (
                "url" in config
                and {"command", "args", "env"}.intersection(config)
                or "command" in config
                and "headers" in config
            ):
                raise ConfigurationError("Mixed stdio and HTTP options.")
            result[name] = ServerConfig(**expand(config))
        return result
    except (OSError, ValueError, AttributeError, KeyError, TypeError) as exc:
        raise ConfigurationError("Invalid MCP servers configuration.") from exc
