# harness/mcp

## Purpose

- Expose allowlisted tools from stdio and Streamable HTTP MCP servers as ordinary tools for a synchronous agent.

## Public interface

- `ServerConfig` is a frozen dataclass. Supply exactly one of `command` (with optional `args` and child `env`) or `url` (with optional static `headers`), plus a nonempty `allowlist`. Shared options are `timeout_seconds` (default 10), and `max_result_bytes` (default 4096).
- `load_mcp_config(path: str | Path) -> dict[str, ServerConfig]` reads the JSON `servers` mapping and expands `${VAR}` in string values including header values. A missing variable raises `EnvVarNotSetError`.
- `MCPRuntime(config: dict[str, ServerConfig], logger: ApplicationLogger)` is a context manager. Inside the context, bind `runtime.tools: list[RemoteTool]` to a `ToolExecutor`. Context exit calls the idempotent `close()` method.
- `RemoteTool` extends `ExternalTool`. Its instance definition uses `strict=False`, and the executor validates arguments against the tool's input schema.

## Contracts

- Entering the runtime opens the configured transports, offers `2025-11-25`, accepts that revision or `2025-06-18` or `2025-03-26`, and reads every page of `tools/list`. The client answers server pings. A startup failure closes all servers opened by that runtime.
- Allowlist entries match exact remote names. Missing names raise `ConfigurationError` with the available names. The agent sees sanitized `server__tool` aliases of at most 64 characters. Alias collisions fail startup.
- Descriptions are clipped to 256 characters. A missing `inputSchema` defaults to `{"type":"object","properties":{}}`.
- Remote content is untrusted tool-result data. Text blocks and embedded resource text are joined with newlines, and each non-text block becomes `[non-text content]`. Success data contains `text` and a boolean `truncated`. Remote call errors raise `ToolExecutionError` and carry a `[truncated=true]` suffix when clipped.

## Dependencies

- Use `harness.tools.ExternalTool` for binding, `harness.exceptions` for errors, and `harness.logger.ApplicationLogger` for logging. Both transports use the Python standard library.
- Keep the dependency direction from `harness.mcp` to `harness.tools`. Both the tools package and the agent base must remain independent of MCP.

## Testing

- Run `uv run pytest tests/test_mcp.py tests/test_mcp_http.py -v`. The suite launches the local stdio fixture in `tests/fixtures/mcp_server.py` and a threaded loopback HTTP fixture with dummy credentials.

## Gotchas

- HTTP uses static headers only. OAuth is unsupported. A timeout marks the connection dead. Reopen the runtime after timeout or session expiry.
- Set per-server `env` to pass additional environment variables to a stdio child. Its effective PATH is used for command lookup.
- Discovery happens once per runtime entry. Keep the runtime open while the executor uses its tools.
- Initialization and all discovery pages share one deadline per server. Each subsequent tool call gets its own deadline.
- The per-server result limit counts the serialized executor response in UTF-8, including JSON escaping and the truncation indicator.
