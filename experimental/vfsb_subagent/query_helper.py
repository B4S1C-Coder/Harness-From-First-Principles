"""Isolated query generation and repair; no investigator history is shared."""

from dataclasses import asdict

from harness.exceptions import ApplicationException, ToolExecutionError
from harness.llms import SyncTextLLMClient
from experimental.vfsb_subagent.log_backend import QueryBackend, bounded_payload


class QueryHelper:
    def __init__(self, backend: QueryBackend, client: SyncTextLLMClient) -> None:
        self.backend = backend
        self.client = client

    def analyze(self, request: str) -> dict:
        messages = [
            {
                "role": "system",
                "content": (
                    "Generate one read-only SQLite SELECT query, without markdown or e"
                    "xplanation. Prefer aggregates and selective filters. Schema: "
                )
                + self.backend.schema,
            },
            {"role": "user", "content": request[:2000]},
        ]
        for _ in range(3):
            try:
                response, _, _ = self.client.generate_next([], messages)
            except ApplicationException:
                return {"error": "Advanced analysis query generator failed."}
            sql = response.choices[0].message.content if response.choices else None
            sql = (sql or "").strip()
            if len(sql.encode()) > 2000:
                error = "Query exceeds 2000 bytes."
            else:
                try:
                    if not sql:
                        raise ToolExecutionError("Empty query.")
                    result = self.backend.query(sql)
                    return bounded_payload({"query": sql, **asdict(result)})
                except ToolExecutionError as exc:
                    error = str(exc)[:300]
            # Keep only the latest failed attempt rather than accumulating repair history.
            messages = messages[:2] + [
                {"role": "assistant", "content": sql[:2000]},
                {"role": "user", "content": "Repair this error: " + error},
            ]
        return {"error": "Advanced analysis failed after three attempts: " + error}
