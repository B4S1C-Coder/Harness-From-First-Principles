"""Ephemeral, read-only query backend for source-preserving log investigations."""

import json
import math
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from harness.exceptions import ToolExecutionError

MAX_BYTES = 4096
MAX_ROWS = 20
LOG_PATTERN = re.compile(
    r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d[,\.]\d+) (\w+) \[(.*?)\] ([^:]+): (.*)$"
)


@dataclass
class QueryResult:
    rows: list[list[Any]] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    truncated: bool = False


def bounded_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Leave room for the executor envelope; retain explicit truncation metadata."""
    while len(json.dumps(payload).encode()) > MAX_BYTES - 128:
        payload["truncated"] = True
        if payload.get("rows"):
            payload["rows"].pop()
        else:
            return {
                "rows": [],
                "truncated": True,
                "error": "Response metadata exceeds output limit.",
            }
    return payload


class QueryBackend(Protocol):
    schema: str

    def query(self, sql: str, parameters: tuple[Any, ...] = ()) -> QueryResult: ...


class SQLiteLogs:
    schema = (
        "logs(filename TEXT, line INTEGER, raw TEXT, timestamp TEXT, level"
        " TEXT, thread TEXT, logger TEXT, message TEXT). timestamp format "
        "YYYY-MM-DD HH:MM:SS,mmm; line is 1-based. Unparsed fields are NUL"
        "L."
    )

    def __init__(self, workspace: Path, timeout_seconds: float = 0.2) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.timeout_seconds = timeout_seconds
        try:
            self.connection.execute(
                
                    "CREATE TABLE logs(filename TEXT, line INTEGER, raw TEXT, timestam"
                    "p TEXT, level TEXT, thread TEXT, logger TEXT, message TEXT)"
                
            )
            for path in sorted(workspace.glob("app-*.log")):
                with path.open(encoding="utf-8", errors="replace", newline="") as source:
                    for number, raw in enumerate(source, 1):
                        match = LOG_PATTERN.match(raw.rstrip("\r\n"))
                        parsed = list(match.groups()) if match else [None] * 5
                        if parsed[0]:
                            parsed[0] = parsed[0].replace(".", ",")
                        self.connection.execute(
                            "INSERT INTO logs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (path.name, number, raw, *parsed),
                        )
            for columns in ("timestamp", "level", "filename, line"):
                self.connection.execute(
                    f"CREATE INDEX idx_{columns.split(',')[0]} ON logs ({columns})"
                )
            self.connection.commit()
            self.connection.execute("PRAGMA query_only = ON")
            self.connection.set_authorizer(self._authorize)
        except (OSError, sqlite3.Error) as exc:
            self.close()
            raise ToolExecutionError("Unable to load application logs.") from exc

    @staticmethod
    def _authorize(
        action: int, arg1: str | None, arg2: str | None, database: str | None, source: str | None
    ) -> int:
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE}
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() not in {
            "load_extension",
            "writefile",
            "readfile",
        }:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

    def query(self, sql: str, parameters: tuple[Any, ...] = ()) -> QueryResult:
        deadline = time.monotonic() + self.timeout_seconds
        self.connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 100)
        # Prevent single huge cells from allocating unbounded response buffers.
        self.connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1024 * 1024)
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, parameters)
            columns = [item[0] for item in cursor.description or []]
            rows = cursor.fetchmany(MAX_ROWS + 1)
            result = QueryResult(
                [[self._json_value(value) for value in row] for row in rows[:MAX_ROWS]],
                columns,
                len(rows) > MAX_ROWS,
            )
            data = bounded_payload(asdict(result))
            return QueryResult(data["rows"], data.get("columns", []), data["truncated"])
        except sqlite3.Error as exc:
            raise ToolExecutionError(f"SQLite query failed: {str(exc)[:300]}") from exc
        finally:
            cursor.close()
            self.connection.set_progress_handler(None, 0)

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, bytes):
            return {"hex": value.hex()}
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        return value

    def overview(self) -> QueryResult:
        return self.query(
            
                "SELECT filename, level, count(*) AS rows, min(timestamp) AS start"
                ", max(timestamp) AS end FROM logs GROUP BY filename, level ORDER "
                "BY filename, level"
            
        )

    def search(
        self,
        start: str | None = None,
        end: str | None = None,
        level: str | None = None,
        filename: str | None = None,
        keyword: str | None = None,
    ) -> QueryResult:
        clauses, parameters = [], []
        for column, operator, value in (
            ("timestamp", ">=", start),
            ("timestamp", "<=", end),
            ("level", "=", level),
            ("filename", "=", filename),
        ):
            if value is not None:
                clauses.append(f"{column} {operator} ?")
                parameters.append(value)
        if keyword is not None:
            clauses.append("instr(raw, ?) > 0")
            parameters.append(keyword)
        return self.query(
            "SELECT * FROM logs WHERE "
            + (" AND ".join(clauses) or "1")
            + " ORDER BY timestamp, filename, line",
            tuple(parameters),
        )

    def nearby(self, filename: str, line: int, radius: int = 3) -> QueryResult:
        return self.query(
            "SELECT * FROM logs WHERE filename = ? AND line BETWEEN ? AND ? ORDER BY line",
            (filename, max(1, line - radius), line + radius),
        )

    def close(self) -> None:
        self.connection.close()
