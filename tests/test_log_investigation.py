import json
from types import SimpleNamespace

import pytest

from experimental.vfsb_subagent.log_backend import SQLiteLogs
from experimental.vfsb_subagent.query_helper import QueryHelper
from harness.exceptions import ToolExecutionError


class FakeClient:
    def __init__(self, replies: list[str]) -> None:
        self.replies = iter(replies)
        self.calls = []

    def generate_next(self, tools: list, messages: list) -> tuple:
        self.calls.append(list(messages))
        return (
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=next(self.replies)))]
            ),
            0,
            0,
        )


@pytest.fixture
def logs(tmp_path):
    (tmp_path / "app-01.log").write_bytes(
        b"2025-01-01 00:00:00,001 ERROR [worker] app.Test: literal %_ failu"
        b"re\r\nstack trace\n2025-01-01 00:00:01,000 INFO [worker] app.Test: r"
        b"ecovered\n"
    )
    backend = SQLiteLogs(tmp_path)
    yield backend
    backend.close()


def test_parse_filters_and_evidence(logs) -> None:
    row = logs.search(
        level="ERROR", keyword="%_", filename="app-01.log", start="2025-01-01", end="2025-01-02"
    ).rows[0]
    # Evidence rows carry each line once: filename, line, timestamp, level, logger, message.
    assert row == [
        "app-01.log",
        1,
        "2025-01-01 00:00:00,001",
        "ERROR",
        "Test",
        "literal %_ failure",
    ]
    # The table still preserves the source line verbatim, including its terminator.
    assert logs.query("SELECT raw FROM logs WHERE line = 1").rows[0][0].endswith("\r\n")
    nearby = logs.nearby("app-01.log", 2, 1)
    assert [row[1] for row in nearby.rows] == [1, 2, 3]
    # An unparsed line (e.g. a stack trace) is returned verbatim in the message slot.
    assert nearby.rows[1] == ["app-01.log", 2, None, None, None, "stack trace"]
    assert logs.query("SELECT count(*) FROM logs").rows == [[3]]
    assert sum(row[2] for row in logs.overview().rows) == 3
    assert logs.search(keyword="absent").rows == []
    assert logs.search(filename="' OR 1=1 --").rows == []


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM logs",
        "DROP TABLE logs",
        "PRAGMA query_only=OFF",
        "ATTACH ':memory:' AS other",
        "CREATE TABLE other(x)",
        "SELECT load_extension('bad')",
        "SELECT * FROM logs; DELETE FROM logs",
    ],
)
def test_read_only(logs, sql) -> None:
    with pytest.raises(ToolExecutionError):
        logs.query(sql)
    assert logs.query("SELECT count(*) FROM logs").rows == [[3]]


def test_timeout_and_bounds(logs) -> None:
    logs.timeout_seconds = 0
    with pytest.raises(ToolExecutionError, match="interrupted"):
        logs.query(
            "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n) SELECT sum(x) FROM n"
        )
    logs.timeout_seconds = 0.2
    result = logs.query(
        "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<30) SELECT x FROM n"
    )
    assert len(result.rows) == 20 and result.truncated
    result = logs.query("SELECT hex(zeroblob(4000))")
    assert result.truncated and not result.rows


def test_repair_and_isolation(logs) -> None:
    client = FakeClient(
        ["SELECT missing FROM logs", "SELECT count(*) FROM logs", "SELECT * FROM logs WHERE 0"]
    )
    helper = QueryHelper(logs, client)
    result = helper.analyze("Count records")
    assert result["rows"] == [[3]] and "missing" not in json.dumps(result)
    assert len(client.calls[1]) == 4
    assert helper.analyze("Empty records")["rows"] == []
    assert len(client.calls[2]) == 2
    assert "Count records" not in json.dumps(client.calls[2])
    failed = QueryHelper(logs, FakeClient(["invalid"] * 3)).analyze("fail")
    assert "three attempts" in failed["error"]


def test_json_values_and_tool_bounds(logs, app_logger) -> None:
    from harness.tools import ToolExecutor
    from experimental.vfsb_subagent.log_tools import (
        LogOverviewTool,
        SearchLogsTool,
        NearbyLogsTool,
        AdvancedLogAnalysisTool,
    )

    assert logs.query("SELECT x'ff', 1e999").rows == [[{"hex": "ff"}, "inf"]]
    executor = ToolExecutor(
        app_logger,
        [
            LogOverviewTool(logs),
            SearchLogsTool(logs),
            NearbyLogsTool(logs),
            AdvancedLogAnalysisTool(QueryHelper(logs, FakeClient(["SELECT hex(zeroblob(4000))"]))),
        ],
    )
    for name, args in [
        ("log_overview", {}),
        ("search_logs", dict.fromkeys(["start", "end", "level", "filename", "keyword"])),
        ("nearby_logs", {"refs": [{"filename": "app-01.log", "line": 1}], "radius": 2}),
        ("advanced_log_analysis", {"request": "large result"}),
    ]:
        output = executor.execute(name, args)
        assert len(output.encode()) <= 4096
        assert json.loads(output)["success"]
        assert "truncated" in json.loads(output)["data"]


def test_incident_evidence_on_sample() -> None:
    from pathlib import Path
    from experimental.vfsb_subagent.log_evidence import scan, timeline, nearby

    db = SQLiteLogs(Path(__file__).resolve().parents[1] / "experimental/data/workspace")
    try:
        signatures = scan(
            db, [{"name": "rm", "alternatives": ["contacting rm", "ERROR IN CONTACTING RM"]}]
        )["signatures"]
        assert signatures["no route"]["count"] > 0
        assert signatures["disk full"]["first_ref"] is None
        assert (
            signatures["rm"]["count"]
            == db.connection.execute(
                "SELECT count(*) FROM logs WHERE lower(raw) LIKE '%contacting rm%'"
            ).fetchone()[0]
        )
        episodes = timeline(db, "2015-10-18 18:06:09", "2015-10-18 18:06:26,029", "app-01.log")[
            "episodes"
        ]
        assert episodes[0]["interleaved"]
        assert episodes[-1]["groups"][0]["level"] == "FATAL"
        refs = [
            signatures["rm"]["first_ref"],
            signatures["rm"]["first_ref"],
            {"filename": "missing", "line": 1},
        ]
        result = nearby(db, refs, 1)
        assert len(result["rows"]) == 3
        assert not result["windows"][-1]["found"]
    finally:
        db.close()
