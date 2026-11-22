"""Timeline, signature scan and search-total behavior on small purpose-built corpora."""

import json
from pathlib import Path

import pytest

from experimental.vfsb_subagent import log_evidence
from experimental.vfsb_subagent.log_backend import SQLiteLogs
from experimental.vfsb_subagent.log_digest import build_digest
from experimental.vfsb_subagent.log_tools import ScanSignaturesTool, SearchLogsTool, TimelineTool
from harness.exceptions import ToolExecutionError
from harness.tools import ToolExecutor

LONG_FATAL = (
    "Task: attempt_1_m_000002_0 - exited : java.net.NoRouteToHostException: No Route to Host "
    "from  MININT-FNANLI5/127.0.0.1 to msra-sa-41:9000 failed on socket timeout exception: "
    "java.net.NoRouteToHostException: No route to host: no further information; "
    "For more details see:  http://wiki.apache.org/hadoop/NoRouteToHost"
)

HADOOP_LINES = [
    "2015-10-18 18:06:08,950 WARN [A] org.apache.hadoop.ipc.Client: Address change detected. "
    "Old: msra-sa-41/10.190.173.170:8030 New: msra-sa-41:8030",
    "2015-10-18 18:06:09,919 WARN [L] org.apache.hadoop.hdfs.LeaseRenewer: Failed to renew lease "
    "for [DFSClient_1] for 72 seconds.  Will retry shortly ...",
    "2015-10-18 18:06:09,966 ERROR [A] org.apache.hadoop.mapreduce.v2.app.rm.RMContainerAllocator: "
    "ERROR IN CONTACTING RM. ",
    "2015-10-18 18:06:10,919 WARN [L] org.apache.hadoop.hdfs.LeaseRenewer: Failed to renew lease "
    "for [DFSClient_1] for 73 seconds.  Will retry shortly ...",
    "2015-10-18 18:06:11,000 WARN [A] org.apache.hadoop.ipc.Client: Address change detected. "
    "Old: msra-sa-41/10.190.173.170:9000 New: msra-sa-41:9000",
    "2015-10-18 18:06:26,029 FATAL [I] org.apache.hadoop.mapred.TaskAttemptListenerImpl: "
    + LONG_FATAL,
    "2015-10-18 18:06:26,100 INFO [A] org.apache.hadoop.ipc.Client: Retrying connect to server: x",
]


@pytest.fixture
def hadoop(tmp_path: Path):
    (tmp_path / "app-01.log").write_text("\n".join(HADOOP_LINES) + "\n")
    db = SQLiteLogs(tmp_path)
    yield db
    db.close()


def test_timeline_groups_carry_time_count_ref_and_full_fatal_text(hadoop: SQLiteLogs) -> None:
    result = log_evidence.timeline(hadoop, None, None, None)
    assert result["columns"] == ["level", "logger", "count", "first", "last", "ref", "message"]
    assert result["omitted_episodes"] == 0 and "next_start" not in result
    first, fatal = result["episodes"]
    lease = next(group for group in first["groups"] if group[1] == "LeaseRenewer")
    # count, first/last within the episode, and a ref that matches the first occurrence
    assert lease[2:6] == [2, "2015-10-18 18:06:09,919", "2015-10-18 18:06:10,919", "app-01.log:2"]
    assert fatal["groups"][0][0] == "FATAL"
    assert fatal["groups"][0][6] == LONG_FATAL  # longer than the 200-character non-fatal limit
    assert len(LONG_FATAL) > 200


def test_timeline_shortens_repeats_and_drops_low_severity_groups_first(tmp_path: Path) -> None:
    def fatal(stamp: str, attempt: str) -> str:
        text = LONG_FATAL.replace("m_000002_0", attempt)
        return f"{stamp} FATAL [I] org.apache.hadoop.mapred.TaskAttemptListenerImpl: {text}"

    noise = [
        f"2015-10-18 18:07:{n:02d},100 WARN [t] app.Noise{n}: {'w' * 190} unique {n}"
        for n in range(30)
    ]
    lines = [
        fatal("2015-10-18 18:06:26,029", "m_000002_0"),
        fatal("2015-10-18 18:06:28,217", "m_000001_0"),
        *noise,
        "2015-10-18 18:07:30,000 ERROR [t] app.Svc: the one error that must survive",
    ]
    (tmp_path / "app-01.log").write_text("\n".join(lines) + "\n")
    db = SQLiteLogs(tmp_path)
    try:
        episodes = log_evidence.timeline(db, None, None, None)["episodes"]
    finally:
        db.close()
    first, second = episodes[0]["groups"][0], episodes[1]["groups"][0]
    assert first[6] == LONG_FATAL
    assert second[6] == LONG_FATAL.replace("m_000002_0", "m_000001_0")[:100]
    last = episodes[-1]
    assert last["omitted_groups"] > 0
    # The ERROR group comes last in time but is kept; the WARN noise is what gets dropped.
    assert "ERROR" in [group[0] for group in last["groups"]]


def test_timeline_null_window_equals_explicit_window(hadoop: SQLiteLogs) -> None:
    explicit = log_evidence.timeline(hadoop, "2015-10-18 18:06:08", "2015-10-18 18:06:27", None)
    assert log_evidence.timeline(hadoop, None, None, None) == explicit
    assert log_evidence.timeline(hadoop, "2015-10-18 18:06:09.919", None, None)["episodes"]
    with pytest.raises(ToolExecutionError):
        log_evidence.timeline(hadoop, "2016", "2015", None)


def test_timeline_reports_where_to_resume_when_episodes_do_not_fit(tmp_path: Path) -> None:
    lines = [
        f"2015-10-18 18:{minute:02d}:00,000 ERROR [t] app.Svc: failure number {'x' * 150} {minute}"
        for minute in range(50)
    ]
    (tmp_path / "app-01.log").write_text("\n".join(lines) + "\n")
    db = SQLiteLogs(tmp_path)
    try:
        result = log_evidence.timeline(db, None, None, None)
        shown = len(result["episodes"])
        assert 0 < shown < 50
        assert result["omitted_episodes"] == 50 - shown
        assert result["next_start"] == f"2015-10-18 18:{shown:02d}:00,000"
        resumed = log_evidence.timeline(db, result["next_start"], None, None)
        assert resumed["episodes"][0]["first"] == result["next_start"]
        assert len(json.dumps(result).encode()) <= 4096
    finally:
        db.close()


def test_scan_lists_zeros_by_name_and_counts_each_custom_alternative(hadoop: SQLiteLogs) -> None:
    result = log_evidence.scan(
        hadoop,
        [
            {
                "name": "rm",
                "alternatives": ["error in contacting rm", "RM communication"],
            }
        ],
    )
    signatures = result["signatures"]
    assert signatures["rm"]["count"] == 1
    # The dead alternative is visible instead of being hidden inside a combined count.
    assert result["custom_alternative_counts"]["rm"] == {
        "error in contacting rm": 1,
        "rm communication": 0,
    }
    assert signatures["lease renew failure"] == {
        "count": 2,
        "first": "2015-10-18 18:06:09,919",
        "last": "2015-10-18 18:06:10,919",
        "first_ref": "app-01.log:2",
    }
    assert {"disk full", "oom", "connection refused"} <= set(result["zero"])
    assert not set(result["zero"]) & set(signatures)
    with pytest.raises(ToolExecutionError):
        log_evidence.scan(hadoop, [{"name": "no route", "alternatives": ["x"]}])


def test_scan_structural_signatures(hadoop: SQLiteLogs) -> None:
    signatures = log_evidence.scan(hadoop, [])["signatures"]
    # Both address-change lines lack an IP in the "New:" address; the "Old:" one has it.
    assert signatures["address change without ip"]["count"] == 2
    assert signatures["loopback host"]["count"] == 1
    assert signatures["loopback host"]["first_ref"] == "app-01.log:6"


def test_scan_does_not_flag_address_change_that_keeps_its_ip(tmp_path: Path) -> None:
    (tmp_path / "app-01.log").write_text(
        "2015-10-18 18:06:08,950 WARN [A] org.apache.hadoop.ipc.Client: Address change detected. "
        "Old: h/10.0.0.1:1 New: h/10.0.0.2:1\n"
    )
    db = SQLiteLogs(tmp_path)
    try:
        assert "address change without ip" in log_evidence.scan(db, [])["zero"]
    finally:
        db.close()


def test_search_reports_total_matches_beyond_the_returned_rows(tmp_path: Path) -> None:
    lines = [f"2015-10-18 18:06:{n % 60:02d},000 ERROR [t] app.Svc: boom {n}" for n in range(45)]
    (tmp_path / "app-01.log").write_text("\n".join(lines) + "\nplain\n")
    db = SQLiteLogs(tmp_path)
    try:
        assert db.count_matches(keyword="boom") == 45
        tool = SearchLogsTool(db)
        keys = ("start", "end", "level", "filename", "keyword")
        one = tool.driver({"queries": [{**dict.fromkeys(keys), "keyword": "boom"}]})
        assert len(one["rows"]) == 20 and one["truncated"] and one["total_matches"] == 45
        many = tool.driver(
            {
                "queries": [
                    {**dict.fromkeys(keys), "keyword": "boom"},
                    {**dict.fromkeys(keys), "keyword": "absent"},
                ]
            }
        )
        assert [g["total_matches"] for g in many["results"]] == [45, 0]
        filtered = dict.fromkeys(keys) | {"keyword": "boom", "filename": "missing", "level": "WARN"}
        empty = tool.driver({"queries": [filtered]})
        assert empty["rows"] == [] and empty["keyword_matches_all_logs"] == 45
        batch = tool.driver({"queries": [filtered, {**filtered, "keyword": "absent"}]})
        assert [r["keyword_matches_all_logs"] for r in batch["results"]] == [45, 0]
        db.query = lambda *a, **k: (_ for _ in ()).throw(ToolExecutionError("slow"))  # type: ignore
        assert db.count_matches(keyword="boom") is None
    finally:
        db.close()


def test_digest_keeps_more_of_a_fatal_message() -> None:
    fatal_stamp, warn_stamp = "2015-10-18 18:06:26,029", "2015-10-18 18:06:27,029"
    groups = [
        ("FATAL", "a.B", 1, 1, fatal_stamp, f"{fatal_stamp}\tf\t1\t{LONG_FATAL}"),
        ("WARN", "a.B", 1, 1, warn_stamp, f"{warn_stamp}\tf\t2\t{LONG_FATAL}"),
    ]
    rows = build_digest({}, {}, groups)["rows"]
    fatal, warn = rows[0][-1], rows[1][-1]
    assert fatal == LONG_FATAL and len(warn) == 200 and warn.endswith("…")


def test_tools_accept_null_timeline_window_and_expose_new_schema(
    hadoop: SQLiteLogs, app_logger
) -> None:
    executor = ToolExecutor(app_logger, [TimelineTool(hadoop), ScanSignaturesTool(hadoop)])
    output = json.loads(
        executor.execute("timeline", {"start": None, "end": None, "filename": None})
    )
    assert output["success"] and output["data"]["episodes"]
    output = json.loads(executor.execute("scan_signatures", {"custom": []}))
    assert output["success"] and "zero" in output["data"]


def test_continuations_inherit_time_only_within_their_file(tmp_path: Path) -> None:
    from contextlib import closing

    stamp = "2015-10-17 14:33:00,000"
    diagnostic = "Container killed on request. Exit code is 137"
    (tmp_path / "app-a.log").write_text(
        f"{stamp} WARN [t] app.Job: Attempt killed\nStack trace\n{diagnostic}\n"
        "2015-10-17 14:32:00,000 INFO [t] app.Job: Delayed message\n"
    )
    (tmp_path / "app-b.log").write_text("Leading fragment\n")
    with closing(SQLiteLogs(tmp_path)) as db:
        row = ["app-a.log", 3, None, None, None, diagnostic]
        for window in ({}, {"start": stamp}, {"end": stamp}, {"start": stamp, "end": stamp}):
            assert db.search(keyword="137", **window).rows == [row]
            assert db.count_matches(keyword="137", **window) == 1
        assert db.count_matches(start=stamp, level="WARN", keyword="137") == 0
        assert db.count_matches(keyword="Leading") == 1
        assert db.count_matches(keyword="Leading", end=stamp) == 0
        assert [r[1] for r in db.search(filename="app-a.log").rows] == [4, 1, 2, 3]
        assert [r[1] for r in db.nearby("app-a.log", 2, 2).rows] == [4, 1, 2, 3]
        nearby = log_evidence.nearby(db, [{"filename": "app-a.log", "line": 2}], 2)
        assert [r[1] for r in nearby["rows"]] == [4, 1, 2, 3]
