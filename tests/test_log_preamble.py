from contextlib import closing
from pathlib import Path

import pytest

from experimental.vfsb_subagent import log_preamble
from experimental.vfsb_subagent.log_backend import SQLiteLogs
from experimental.vfsb_subagent.log_evidence import timeline
from experimental.vfsb_subagent.log_pivots import select_pivots
from experimental.vfsb_subagent.log_tools import (
    IncidentDigestTool,
    NearbyLogsTool,
    ScanSignaturesTool,
    TimelineTool,
)
from harness.logger import ApplicationLogger
from harness.tools import ToolExecutor


def event(level: str, logger: str, message: str, second: int = 0) -> str:
    return f"2026-10-01 00:00:{second:02d},000 {level} [t] {logger}: {message}\n"


@pytest.mark.parametrize("level", ["CRITICAL", "SEVERE", "FATAL"])
def test_pivots_order_ties_and_group_by_full_logger(tmp_path: Path, level: str) -> None:
    first = tmp_path / "app-east.log"
    first.write_text(
        event("INFO", "meters.Reader", "read") * 8
        + event("ERROR", "meters.Reader", "sensor 21 drifted")
        + event("ERROR", "meters.Reader", "sensor 22 drifted")
        + event("ERROR", "clocks.Reader", "sensor 23 drifted")
    )
    (tmp_path / "app-west.log").write_text(
        event(level, "safety.Interlock", "lock engaged") + event("FATAL", "later", "other", 1)
    )
    with closing(SQLiteLogs(tmp_path)) as db:
        pivots, omitted = select_pivots(db)
    assert omitted == 0
    assert [(p.filename, p.line, p.reasons) for p in pivots] == [
        ("app-west.log", 1, ["first fatal"]),
        (first.name, 9, ["earliest episode", "first ERROR in family"]),
        (first.name, 11, ["first ERROR in family"]),
    ]


def test_pivots_precede_display_truncation_and_count_excess_families(tmp_path: Path) -> None:
    path = tmp_path / "app-sensors.log"
    path.write_text(
        event("WARN", "clock", "drifting")
        + "".join(event("ERROR", f"sensor.{n}", "overheated " + "x" * 180) for n in range(30))
        + event("CRITICAL", "controller", "stopped", 1)
    )
    with closing(SQLiteLogs(tmp_path)) as db:
        displayed = timeline(db, None, None, None)["episodes"][0]["groups"]
        pivots, omitted = select_pivots(db)
    assert all(row[5] != f"{path.name}:1" for row in displayed)
    assert [p.line for p in pivots] == [32, 1, 2, 3, 4, 5, 6, 7]
    assert omitted == 24


@pytest.mark.parametrize("content", ["", "unparsed\n", event("INFO", "journal", "saved")])
def test_no_qualifying_events(tmp_path: Path, content: str) -> None:
    (tmp_path / "app-journal.log").write_text(content)
    with closing(SQLiteLogs(tmp_path)) as db:
        assert select_pivots(db) == ([], 0)


def test_one_batched_lookup_includes_continuations_and_marks_clipped_windows(
    tmp_path: Path, app_logger: ApplicationLogger, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "app-sensors.log"
    path.write_text(
        event("ERROR", "sensor", "sampling stalled")
        + "unparsed diagnostic\n"
        + event("FATAL", "controller", "suspended", 1)
        + "x" * 5000
        + "\n"
    )
    with closing(SQLiteLogs(tmp_path)) as db:
        tools = [
            tool(db)
            for tool in (IncidentDigestTool, ScanSignaturesTool, TimelineTool, NearbyLogsTool)
        ]
        executor = ToolExecutor(app_logger, tools)
        calls = []
        execute = executor.execute

        def record(name: str, args: dict) -> str:
            calls.append((name, args))
            return execute(name, args)

        monkeypatch.setattr(executor, "execute", record)
        nearby = log_preamble.collect(db, executor)["nearby_logs"]
    assert calls == [
        *log_preamble.DEFAULT_CALLS.items(),
        (
            "nearby_logs",
            {"refs": [{"filename": path.name, "line": n} for n in [3, 1]], "radius": 1},
        ),
    ]
    assert [row[1] for row in nearby["rows"]] == [1, 2, 3]
    assert nearby["rows"][1][-1] == "unparsed diagnostic"
    assert nearby["truncated"] and [p["clipped"] for p in nearby["pivots"]] == [True, False]
