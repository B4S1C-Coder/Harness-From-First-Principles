import json

import pytest

from experimental.vfsb_subagent.log_backend import DIGEST_TIMEOUT_SECONDS, SQLiteLogs
from experimental.vfsb_subagent.log_digest import DIGEST_BYTES, build_digest, normalize
from experimental.vfsb_subagent.log_tools import IncidentDigestTool
from harness.exceptions import ToolExecutionError
from harness.tools import ToolExecutor


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Progress of TaskAttempt attempt_1445144423722_0020_m_000001_0 is : 0.37551183",
            "Progress of TaskAttempt attempt_<ID> is : <N>",
        ),
        (
            "Address change detected. Old: msra-sa-41/10.190.173.170:8030 New: msra-sa-41:8030",
            "Address change detected. Old: msra-sa-41/<IP>:<N> New: msra-sa-41:<N>",
        ),
        (
            "Failed to renew lease for [DFSClient_NONMAPREDUCE_1537864556_1] for 72 seconds.  Go",
            "Failed to renew lease for [DFSClient_NONMAPREDUCE_<N>_<N>] for <N> seconds. Go",
        ),
        (
            "Error Recovery for block BP-1347369012-10.190.173.170-1444972147527:blk_1073743512_"
            "2731 bad datanode 10.86.164.9:50010",
            "Error Recovery for block BP-<ID>:blk_<ID> bad datanode <IP>:<N>",
        ),
        ("took 65020ms (threshold=30000ms)", "took <N>ms (threshold=<N>ms)"),
        # Hostnames keep their digits; loopback and wildcard addresses stay visible.
        (
            "No Route to Host from MININT-FNANLI5/127.0.0.1 to node-7:9000",
            "No Route to Host from MININT-FNANLI5/127.0.0.1 to node-7:<N>",
        ),
        ("bind 0.0.0.0:8030 failed", "bind 0.0.0.0:<N> failed"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_normalize_handles_null() -> None:
    assert normalize(None) is None


LOG = (
    "2025-01-01 00:00:01,000 INFO [t] app.Svc: started job_1_0001\n"
    "2025-01-01 00:00:02,000 WARN [t] app.Net: retry 1 of 10 to host-3:8030\n"
    "2025-01-01 00:00:03,000 WARN [t] app.Net: retry 2 of 10 to host-3:8030\n"
    "2025-01-01 00:00:04,000 ERROR [t] app.Svc: lost contact with host-3:8030\n"
    "java.net.ConnectException: stack line without a timestamp\n"
    "2025-01-01 00:00:05,000 FATAL [t] app.Svc: giving up after 99 attempts\n"
)


@pytest.fixture
def backend(tmp_path):
    (tmp_path / "app-01.log").write_text(LOG)
    (tmp_path / "app-02.log").write_text(
        "2025-01-01 00:00:06,000 WARN [t] app.Net: retry 3 of 10 to host-3:8030\n"
    )
    logs = SQLiteLogs(tmp_path)
    yield logs
    logs.close()


def test_digest_groups_and_orders(backend: SQLiteLogs) -> None:
    digest = backend.digest()
    assert digest["corpus"] == {
        "lines": 7,
        "files": 2,
        "start": "2025-01-01 00:00:01,000",
        "end": "2025-01-01 00:00:06,000",
    }
    assert digest["scope"]["lines_by_level"] == {"ERROR": 1, "FATAL": 1, "INFO": 1, "WARN": 3}
    assert digest["scope"]["unparsed_lines"] == 1
    assert digest["scope"]["templates"] == 3 and digest["scope"]["lines_in_templates"] == 5
    assert "INFO" not in {row[0] for row in digest["rows"]}
    retry = next(row for row in digest["rows"] if row[1] == "Net")
    # level, logger, count, files, first, last, first_ref, message. The message is the verbatim
    # first occurrence, never the masked grouping template.
    assert retry == [
        "WARN",
        "Net",
        3,
        2,
        "2025-01-01 00:00:02,000",
        "2025-01-01 00:00:06,000",
        "app-01.log:2",
        "retry 1 of 10 to host-3:8030",
    ]
    assert not any("<N>" in row[7] or "<IP>" in row[7] for row in digest["rows"])
    firsts = [row[4] for row in digest["rows"]]
    assert firsts == sorted(firsts) and not digest["truncated"] and "omitted" not in digest


def test_digest_filters(backend: SQLiteLogs) -> None:
    assert [r[0] for r in backend.digest(level="ERROR")["rows"]] == ["ERROR"]
    assert [r[2] for r in backend.digest(filename="app-02.log")["rows"]] == [1]
    windowed = backend.digest(start="2025-01-01 00:00:04", end="2025-01-01 00:00:05,500")
    assert {r[0] for r in windowed["rows"]} == {"ERROR", "FATAL"}
    assert windowed["scope"]["filters"] == {
        "start": "2025-01-01 00:00:04",
        "end": "2025-01-01 00:00:05,500",
    }
    assert backend.digest(filename="' OR 1=1 --")["rows"] == []


def test_digest_does_not_disturb_query_limits(backend: SQLiteLogs) -> None:
    """The digest installs its own progress handler; ad-hoc queries must keep theirs."""
    backend.digest()
    backend.timeout_seconds = 0
    with pytest.raises(ToolExecutionError, match="interrupted"):
        backend.query(
            "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n) SELECT sum(x) FROM n"
        )
    backend.timeout_seconds = 0.2
    assert backend.query("SELECT count(*) FROM logs").rows == [[7]]
    assert DIGEST_TIMEOUT_SECONDS > backend.timeout_seconds


def test_digest_timeout_is_a_tool_error(tmp_path, monkeypatch) -> None:
    # SQLite checks the progress handler every 1000 VM ops, so the corpus must be non-trivial.
    template = "2025-01-01 00:00:00,{:03d} WARN [t] app.Net: retry {}\n"
    (tmp_path / "app-01.log").write_text(
        "".join(template.format(i % 1000, i) for i in range(3000))
    )
    logs = SQLiteLogs(tmp_path)
    try:
        monkeypatch.setattr("experimental.vfsb_subagent.log_backend.DIGEST_TIMEOUT_SECONDS", -1)
        with pytest.raises(ToolExecutionError, match="timed out"):
            logs.digest()
    finally:
        logs.close()


def test_tmpl_is_usable_from_analysis_queries(backend: SQLiteLogs) -> None:
    rows = backend.query(
        "SELECT tmpl(message), count(*) FROM logs WHERE level = 'WARN' GROUP BY 1"
    ).rows
    assert rows == [["retry <N> of <N> to host-3:<N>", 3]]


def test_digest_prefers_severity_and_reports_omissions() -> None:
    groups = [
        (
            "WARN",
            "a.Noisy",
            50,
            1,
            "2025-01-01 00:00:01,000",
            f"2025-01-01 00:00:0{i % 10},000\tapp-01.log\t{i + 1:010d}\tnoisy message {i}",
        )
        for i in range(60)
    ] + [
        (
            "FATAL",
            "a.Core",
            1,
            1,
            "2025-01-01 00:09:00,000",
            "2025-01-01 00:09:00,000\tapp-01.log\t0000000999\tfatal\tone",  # tab kept in message
        ),
    ]
    digest = build_digest({"lines": 1}, {"filters": {}}, groups, byte_budget=1500)
    levels = [row[0] for row in digest["rows"]]
    assert "FATAL" in levels and len(digest["rows"]) < 61
    assert next(r[7] for r in digest["rows"] if r[0] == "FATAL") == "fatal\tone"
    assert digest["truncated"]
    assert digest["omitted"]["templates"] + len(digest["rows"]) == 61
    assert digest["omitted"]["lines_by_level"] == {"WARN": digest["omitted"]["lines"]}
    assert len(json.dumps(digest, ensure_ascii=False).encode()) <= 1500


def test_tool_schema_execution_and_budget(backend: SQLiteLogs, app_logger) -> None:
    executor = ToolExecutor(app_logger, [IncidentDigestTool(backend)])
    args = dict.fromkeys(["start", "end", "level", "filename"])
    output = executor.execute("incident_digest", args)
    assert len(output.encode()) <= DIGEST_BYTES + 128
    assert json.loads(output)["success"]
    rejected = json.loads(executor.execute("incident_digest", {}))
    assert rejected["success"] is False
