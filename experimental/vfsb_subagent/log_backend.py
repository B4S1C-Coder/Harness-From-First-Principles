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
from experimental.vfsb_subagent.log_digest import QUIET_LEVELS, build_digest, normalize

MAX_BYTES = 4096
MAX_ROWS = 20
# The digest scans every non-INFO line, so it gets a larger time budget than ad-hoc queries.
DIGEST_TIMEOUT_SECONDS = 10.0
MAX_DIGEST_GROUPS = 5000
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


def _short_name(name: str | None) -> str | None:
    return None if name is None else name.rsplit(".", 1)[-1]


# Evidence rows returned to the model: each source line appears once. `raw` and `thread` stay in
# the table (keyword search and advanced_log_analysis still see them) but are not echoed per row,
# and an unparsed line (stack trace, continuation) is returned verbatim in the message slot.
EVIDENCE_COLUMNS = (
    "filename, line, timestamp, level, logger_name(logger) AS logger,"
    " CASE WHEN timestamp IS NULL THEN rtrim(raw, char(13, 10)) ELSE message END AS message"
)


class SQLiteLogs:
    schema = (
        "logs(filename TEXT, line INTEGER, raw TEXT, timestamp TEXT, level"
        " TEXT, thread TEXT, logger TEXT, message TEXT). timestamp format "
        "YYYY-MM-DD HH:MM:SS,mmm; line is 1-based. Unparsed fields are NUL"
        "L. SQL function tmpl(message) masks numbers/ids/IPs so similar mes"
        "sages share one value; use it to GROUP BY message type."
    )

    def __init__(self, workspace: Path, timeout_seconds: float = 0.2) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.timeout_seconds = timeout_seconds
        try:
            self.connection.create_function("tmpl", 1, normalize, deterministic=True)
            self.connection.create_function("logger_name", 1, _short_name, deterministic=True)
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
            f"SELECT {EVIDENCE_COLUMNS} FROM logs WHERE "
            + (" AND ".join(clauses) or "1")
            + " ORDER BY timestamp, filename, line",
            tuple(parameters),
        )

    def digest(
        self,
        start: str | None = None,
        end: str | None = None,
        level: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Group non-INFO lines (or one `level`) by masked message template; see log_digest."""
        scope, parameters, filters = [], [], {}
        for key, column, operator, value in (
            ("start", "timestamp", ">=", start),
            ("end", "timestamp", "<=", end),
            ("filename", "filename", "=", filename),
        ):
            if value is not None:
                scope.append(f"{column} {operator} ?")
                parameters.append(value)
                filters[key] = value
        scope_where = " AND ".join(scope) or "1"
        if level is not None:
            level_where, level_parameters = "level = ?", [level]
            filters["level"] = level
        else:
            level_where = "level IS NOT NULL AND level NOT IN (?, ?, ?)"
            level_parameters = list(QUIET_LEVELS)

        deadline = time.monotonic() + DIGEST_TIMEOUT_SECONDS
        self.connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        cursor = self.connection.cursor()
        try:
            total, files, first, last = cursor.execute(
                "SELECT count(*), count(DISTINCT filename), min(timestamp), max(timestamp)"
                " FROM logs"
            ).fetchone()
            by_level = dict(
                cursor.execute(
                    f"SELECT level, count(*) FROM logs WHERE {scope_where} GROUP BY level",
                    parameters,
                ).fetchall()
            )
            groups = cursor.execute(
                "SELECT level, logger, t, count(*), count(DISTINCT filename), max(timestamp),"
                " min(timestamp || char(9) || filename || char(9) || printf('%010d', line))"
                " FROM (SELECT level, logger, tmpl(message) AS t, timestamp, filename, line"
                f" FROM logs WHERE {scope_where} AND {level_where})"
                " GROUP BY level, logger, t",
                [*parameters, *level_parameters],
            ).fetchmany(MAX_DIGEST_GROUPS + 1)
        except sqlite3.Error as exc:
            if "interrupted" in str(exc):
                raise ToolExecutionError(
                    "Digest timed out; narrow start/end or set filename."
                ) from exc
            raise ToolExecutionError(f"Digest failed: {str(exc)[:300]}") from exc
        finally:
            cursor.close()
            self.connection.set_progress_handler(None, 0)

        capped = len(groups) > MAX_DIGEST_GROUPS
        return build_digest(
            {"lines": total, "files": files, "start": first, "end": last},
            {
                "filters": filters,
                "lines_by_level": {k: v for k, v in by_level.items() if k is not None},
                "unparsed_lines": by_level.get(None, 0),
            },
            groups[:MAX_DIGEST_GROUPS],
            groups_capped=capped,
        )

    def nearby(self, filename: str, line: int, radius: int = 3) -> QueryResult:
        return self.query(
            f"SELECT {EVIDENCE_COLUMNS} FROM logs"
            " WHERE filename = ? AND line BETWEEN ? AND ? ORDER BY line",
            (filename, max(1, line - radius), line + radius),
        )

    def close(self) -> None:
        self.connection.close()
