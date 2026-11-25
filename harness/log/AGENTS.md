SQLiteLogs accepts a workspace Path or a synchronous LogSource. Implement lines() to yield a finite batch of (logical source name, raw line) pairs. Sources may interleave. Each name has independent one-based line numbers and continuation timestamps. The resulting SQLite snapshot is read-only. Close it after the investigation.

Supply log_tools instances to the agent executor. InvestigationAgent and InvestigationConfig implement the evidence preamble and turn-local retrieval policy. QueryHelper accepts a query backend and a synchronous Chat Completions client.
