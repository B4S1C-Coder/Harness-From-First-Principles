from collections.abc import Iterator
from contextlib import closing

from harness.log.log_backend import SQLiteLogs


def test_interleaved_source_keeps_independent_positions_and_timestamps() -> None:
    class Batch:
        def lines(self) -> Iterator[tuple[str, str]]:
            yield "a", "2015-01-01 00:00:01.000 WARN [t] log: first\n"
            yield "b", "unparsed\n"
            yield "a", "continuation\r\n"

    with closing(SQLiteLogs(Batch())) as db:
        assert db.query("SELECT filename,line,raw,effective_ts FROM logs ORDER BY rowid").rows == [
            ["a", 1, "2015-01-01 00:00:01.000 WARN [t] log: first\n", "2015-01-01 00:00:01,000"],
            ["b", 1, "unparsed\n", None],
            ["a", 2, "continuation\r\n", "2015-01-01 00:00:01,000"],
        ]
