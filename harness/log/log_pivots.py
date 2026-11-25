"""Choose the first source anchors from the same events the timeline covers."""

import sqlite3
import time
from dataclasses import dataclass, field

from harness.exceptions import ToolExecutionError
from .log_backend import DIGEST_TIMEOUT_SECONDS, SQLiteLogs
from .log_digest import QUIET_LEVELS, SEVERITY, normalize

MAX_PIVOTS = 8


@dataclass
class Pivot:
    filename: str
    line: int
    reasons: list[str] = field(default_factory=list)


def select_pivots(db: SQLiteLogs) -> tuple[list[Pivot], int]:
    """Inspect source events before the digest or timeline drops display rows."""
    order = "ORDER BY timestamp, filename, line"
    quiet = ",".join("?" for _ in QUIET_LEVELS)
    deadline = time.monotonic() + DIGEST_TIMEOUT_SECONDS
    db.connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
    first_event = first_fatal = None
    families: set[tuple[str, str | None]] = set()
    first_errors: list[tuple[str, int]] = []
    try:
        for file, line, level, logger, message in db.connection.execute(
            f"SELECT filename, line, level, logger, message FROM logs "
            f"WHERE timestamp IS NOT NULL AND level NOT IN ({quiet}) {order}",
            QUIET_LEVELS,
        ):
            ref = (file, line)
            if first_event is None:
                first_event = ref
            severity = SEVERITY.get(level.upper(), 1)
            if severity == 3 and first_fatal is None:
                first_fatal = ref
            if severity == 2:
                key = (logger, normalize(message))
                if key not in families:
                    families.add(key)
                    if len(first_errors) < MAX_PIVOTS:
                        first_errors.append(ref)
    except sqlite3.Error as exc:
        raise ToolExecutionError(f"Pivot selection failed: {exc}") from exc
    finally:
        db.connection.set_progress_handler(None, 0)

    selected: dict[tuple[str, int], Pivot] = {}
    candidates = [(first_fatal, "first fatal"), (first_event, "earliest episode")]
    candidates.extend((ref, "first ERROR in family") for ref in first_errors)
    for ref, reason in candidates:
        if ref is None:
            continue
        if ref not in selected:
            if len(selected) == MAX_PIVOTS:
                continue
            selected[ref] = Pivot(*ref)
        selected[ref].reasons.append(reason)
    included_families = sum(ref in selected for ref in first_errors)
    return list(selected.values()), len(families) - included_families
