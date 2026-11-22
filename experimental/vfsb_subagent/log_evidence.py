"""Deterministic multi-line evidence tools."""

import json
import re
import time
from datetime import datetime
from typing import Any

from harness.exceptions import ToolExecutionError
from .log_backend import DIGEST_TIMEOUT_SECONDS, SQLiteLogs, EVIDENCE_COLUMNS, MAX_BYTES
from .log_digest import FATAL_MESSAGE_CHARS, MAX_MESSAGE_CHARS, SEVERITY, normalize

FATAL_LEVELS = ("FATAL", "CRITICAL", "SEVERE")
# A message type already shown in full in an earlier episode only needs enough text to tell the
# occurrences apart (e.g. the attempt id at its start).
REPEAT_MESSAGE_CHARS = 100

CATALOG = {
    "unresolved host": (
        "unknownhostexception",
        "unresolvedaddress",
        "unresolved host",
        "<unresolved>",
        "name or service not known",
    ),
    "connection refused": ("connection refused",),
    "no route": ("no route to host", "noroutetohostexception"),
    "disk full": ("disk full", "no space left on device", "enospc"),
    "oom": ("outofmemoryerror", "out of memory", "oomkilled"),
    "container killed": ("container killed", "killed container", "oomkilled"),
    "socket timeout": ("sockettimeoutexception", "socket timeout"),
    "safe mode": ("safemodeexception", "safe mode"),
    # Hadoop/HDFS. Patterns (not literals) are for structure a substring cannot express.
    "lease renew failure": ("failed to renew lease",),
    "rm contact failure": ("error in contacting rm", "error communicating with rm"),
    # The new address has no resolved IP, e.g. "Old: host/10.0.0.1:8030 New: host:8030".
    "address change without ip": (
        re.compile(r"address change detected\. old: \S+ new: [^/\s]+:\d+\s*$", re.I),
    ),
    "loopback host": (re.compile(r"[A-Za-z][\w.-]*/127\.0\.0\.1\b"),),
}


TIMELINE_COLUMNS = ["level", "logger", "count", "first", "last", "ref", "message"]


def fits(payload: dict) -> bool:
    return len(json.dumps(payload).encode()) <= MAX_BYTES - 128


def _hit(term: str | re.Pattern[str], raw: str, folded: str) -> bool:
    return bool(term.search(raw)) if isinstance(term, re.Pattern) else term in folded


def scan(db: SQLiteLogs, custom: list[dict]) -> dict:
    """Count catalog and custom signatures. A custom entry is one mechanism; its alternatives
    are spellings of the same message, and each alternative gets its own count."""
    catalog: dict[str, tuple[str | re.Pattern[str], ...]] = dict(CATALOG)
    custom_names = []
    for item in custom:
        name = item["name"]
        if name in catalog:
            raise ToolExecutionError("Signature names must be unique.")
        catalog[name] = tuple(term.casefold() for term in item["alternatives"])
        custom_names.append(name)
    rows = {name: dict(count=0, first=None, last=None, first_ref=None) for name in catalog}
    terms = {name: dict.fromkeys(catalog[name], 0) for name in custom_names}
    previous_file = previous_time = None
    deadline = time.monotonic() + DIGEST_TIMEOUT_SECONDS
    for number, (filename, line, stamp, raw) in enumerate(
        db.connection.execute("SELECT filename,line,timestamp,raw FROM logs ORDER BY filename,line")
    ):
        if number % 1024 == 0 and time.monotonic() > deadline:
            raise ToolExecutionError("Signature scan timed out.")
        if filename != previous_file or stamp:
            previous_time = stamp
        previous_file = filename
        folded = raw.casefold()
        for name, alternatives in catalog.items():
            matched = [term for term in alternatives if _hit(term, raw, folded)]
            if not matched:
                continue
            for term in matched:
                if name in terms:
                    terms[name][term] += 1
            row = rows[name]
            if not row["count"] or (
                previous_time and (not row["first"] or previous_time < row["first"])
            ):
                row.update(first=previous_time, first_ref=f"{filename}:{line}")
            if previous_time and (not row["last"] or previous_time > row["last"]):
                row["last"] = previous_time
            row["count"] += 1
    # Zeros are evidence too, but a name costs far less than a row of nulls.
    result: dict[str, Any] = dict(
        signatures={name: row for name, row in rows.items() if row["count"]},
        zero=[name for name, row in rows.items() if not row["count"]],
    )
    if terms:
        result["custom_alternative_counts"] = terms
    if not fits(result):
        raise ToolExecutionError(
            "Signature summaries exceed the output budget. Reduce custom signatures."
        )
    return result


def _drop_least_severe(groups: list[list]) -> None:
    """Remove the lowest-severity group, the latest one on ties, so FATAL/ERROR rows survive."""
    ranks = [SEVERITY.get((group[0] or "").upper(), 1) for group in groups]
    groups.pop(len(ranks) - 1 - ranks[::-1].index(min(ranks)))


def timeline(db: SQLiteLogs, start: str | None, end: str | None, filename: str | None) -> dict:
    """Warning and failure episodes in time order. Null start/end span the whole corpus."""
    start = start.replace(".", ",") if start else ""
    end = end.replace(".", ",") if end else "\uffff"
    if start > end:
        raise ToolExecutionError("Start must precede end.")
    events = db.connection.execute(
        f"SELECT {EVIDENCE_COLUMNS} FROM logs WHERE timestamp BETWEEN ? AND ? "
        "AND (? IS NULL OR filename=?) AND level NOT IN ('INFO','DEBUG','TRACE') "
        "ORDER BY timestamp,filename,line",
        (start, end, filename, filename),
    )
    episodes: list[dict[str, Any]] = []
    groups: dict[tuple, list] = {}
    shown: set[tuple] = set()
    previous = last_key = None
    after_critical = False
    deadline = time.monotonic() + DIGEST_TIMEOUT_SECONDS
    for number, (file, line, stamp, level, logger, msg) in enumerate(events):
        if number % 1024 == 0 and time.monotonic() > deadline:
            raise ToolExecutionError("Timeline timed out; narrow start/end or set filename.")
        moment = datetime.fromisoformat(stamp)
        critical = level in FATAL_LEVELS
        if (
            previous is None
            or critical
            or after_critical
            or (moment - previous).total_seconds() > 5
        ):
            episode = dict(first=stamp, last=stamp, groups=[], interleaved=False)
            episodes.append(episode)
            groups = {}
            last_key = None
        key = (level, logger, normalize(msg))
        if key not in groups:
            limit = FATAL_MESSAGE_CHARS if critical else MAX_MESSAGE_CHARS
            if key in shown:
                limit = min(limit, REPEAT_MESSAGE_CHARS)
            shown.add(key)
            # [level, logger, count, first, last, ref, message]; first/last are within the episode.
            groups[key] = [level, logger, 0, stamp, stamp, f"{file}:{line}", msg[:limit]]
            episode["groups"].append(groups[key])
        elif key != last_key:
            episode["interleaved"] = True
        groups[key][2] += 1
        groups[key][4] = stamp
        episode["last"] = stamp
        previous, last_key, after_critical = moment, key, critical
    result: dict[str, Any] = dict(
        columns=TIMELINE_COLUMNS, episodes=[], omitted_episodes=len(episodes)
    )
    for episode in episodes:
        result["episodes"].append(episode)
        result["omitted_episodes"] -= 1
        episode["omitted_groups"] = 0
        while episode["groups"] and not fits(result):
            _drop_least_severe(episode["groups"])
            episode["omitted_groups"] += 1
        if not episode["groups"]:
            result["episodes"].pop()
            result["omitted_episodes"] += 1
            result["next_start"] = episode["first"]  # re-run from here to see the rest
            break
    return result


def nearby(db: SQLiteLogs, refs: list[dict], radius: int) -> dict[str, Any]:
    windows = []
    candidates = {}
    order = {}
    result = dict(rows=[], windows=windows, truncated=False)
    for ref in refs:
        file, line = ref["filename"], ref["line"]
        rows = list(
            db.connection.execute(
                f"SELECT {EVIDENCE_COLUMNS}, effective_ts FROM logs WHERE filename=? "
                "AND line BETWEEN ? AND ? ORDER BY line",
                (file, line - radius, line + radius),
            )
        )
        found = any(row[1] == line for row in rows)
        windows.append(dict(**ref, found=found, clipped=False))
        if found:
            for row in rows:
                *evidence, stamp = row
                row = tuple(evidence)
                order[row] = (stamp or "", file, row[1])
                distance = abs(row[1] - line)
                candidates[row] = min(distance, candidates.get(row, distance))
    for row in sorted(candidates, key=lambda row: (candidates[row], row[:2])):
        result["rows"].append(row)
        if not fits(result):
            result["rows"].pop()
            result["truncated"] = True
            for window in windows:
                if (
                    window["found"]
                    and window["filename"] == row[0]
                    and abs(window["line"] - row[1]) <= radius
                ):
                    window["clipped"] = True
    result["rows"].sort(key=order.__getitem__)
    return result
