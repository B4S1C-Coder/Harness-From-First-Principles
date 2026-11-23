# Synchronous MCP tools

Load a JSON servers mapping with load_mcp_config(path), or construct ServerConfig objects.
MCPRuntime(config, logger) owns one stdio subprocess per server for the context lifetime.
Bind runtime.tools to ToolExecutor inside the context. Startup is all-or-nothing.
The client supports MCP 2025-11-25 tools and ping. Discovery occurs once at startup.
Allowlist entries match exact remote names. Conflicting public aliases fail startup.
Remote text stays in tool results. Non-text blocks become placeholders.
The per-server result limit counts the serialized executor envelope in UTF-8.
