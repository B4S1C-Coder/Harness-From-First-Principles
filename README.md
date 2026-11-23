# Harness from First Principles
A harness being built from first principles to understand what even is an harness. The [`harness/`](./harness/) folder contains the harness (from first principles) as a framework. The harness is being made incrementally by introducing new features whilst addressing any shortcomings in the existing ones. So it's best to make this as a reusable framework as opposed to a task specific harness.

Check out the examples folder and readme's there for illustration.

## MCP tools over stdio

Supply a local server executable and allowlist its remote tool names. This placeholder
GitHub configuration assumes the executable and read-only credential are provided locally.

```json
{"servers":{"github":{"command":"github-mcp-server","args":["stdio"],
  "env":{"GITHUB_PERSONAL_ACCESS_TOKEN":"${GITHUB_TOKEN}"},
  "allowlist":["issue_read"]}}}
```

```python
from harness.mcp import MCPRuntime, load_mcp_config
from harness.tools import ToolExecutor

with MCPRuntime(load_mcp_config("servers.json"), logger) as runtime:
    executor = ToolExecutor(logger, runtime.tools)
    tools = list(executor.definitions().values())
    # Run the agent here with these definitions and this executor.
```

Each server accepts timeout_seconds (default 10) and max_result_bytes (default 4096).

For a hosted server, use a URL and static headers. This GitHub example exposes
one read-only tool and reads its bearer token from the environment.

```json
{"servers":{"github":{"url":"https://api.githubcopilot.com/mcp/",
  "headers":{"Authorization":"Bearer ${GITHUB_TOKEN}"},
  "allowlist":["issue_read"]}}}
```

HTTP endpoints require HTTPS except on localhost and 127.0.0.1. Authentication
uses static headers only. OAuth flows are unsupported. A timeout marks the
connection dead. Reopen the runtime after a timeout or expired session.
