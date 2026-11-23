import json
import math
import os
from pathlib import Path
import re
from dataclasses import dataclass, field

from harness.exceptions import ConfigurationError, EnvVarNotSetError


@dataclass(frozen=True)
class ServerConfig:
    command: str
    allowlist: list[str]
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict, repr=False)
    timeout_seconds: float = 10
    max_result_bytes: int = 4096

    def __post_init__(self) -> None:
        if not isinstance(self.command, str) or not self.command:
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
        return {name: ServerConfig(**expand(config)) for name, config in servers.items()}
    except (OSError, ValueError, AttributeError, KeyError, TypeError) as exc:
        raise ConfigurationError("Invalid MCP servers configuration.") from exc
