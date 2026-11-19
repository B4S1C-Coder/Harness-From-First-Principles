"""Deterministic multi-line evidence tools."""

import json
from datetime import datetime
from typing import Any

from harness.exceptions import ToolExecutionError
from .log_backend import SQLiteLogs, EVIDENCE_COLUMNS, MAX_BYTES
from .log_digest import normalize

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
}


def fits(payload: dict) -> bool:
    return len(json.dumps(payload).encode()) <= MAX_BYTES - 128


def scan(db: SQLiteLogs, custom: list[dict]) -> dict:
    catalog = dict(CATALOG)
    for item in custom:
        name = item["name"]
        if name in catalog:
            raise ToolExecutionError("Signature names must be unique.")
        catalog[name] = tuple(term.casefold() for term in item["alternatives"])
    rows = {name: dict(count=0, first=None, last=None, first_ref=None) for name in catalog}
    previous_file = previous_time = None
    for filename, line, stamp, raw in db.connection.execute(
        "SELECT filename,line,timestamp,raw FROM logs ORDER BY filename,line"
    ):
        if filename != previous_file or stamp:
            previous_time = stamp
        previous_file = filename
        raw = raw.casefold()
        for name, terms in catalog.items():
            if any(term in raw for term in terms):
                row = rows[name]
                if not row["count"] or (
                    previous_time and (not row["first"] or previous_time < row["first"])
                ):
                    row.update(first=previous_time, first_ref=dict(filename=filename, line=line))
                if previous_time and (not row["last"] or previous_time > row["last"]):
                    row["last"] = previous_time
                row["count"] += 1
    result = dict(signatures=rows)
    if not fits(result):
        raise ToolExecutionError(
            "Signature summaries exceed the output budget. Reduce custom signatures."
        )
    return result


def timeline(db: SQLiteLogs, start: str, end: str, filename: str | None) -> dict:
    start, end = start.replace(".", ","), end.replace(".", ",")
    if start > end:
        raise ToolExecutionError("Start must precede end.")
    events = db.connection.execute(
        f"SELECT {EVIDENCE_COLUMNS} FROM logs WHERE timestamp BETWEEN ? AND ? "
        "AND (? IS NULL OR filename=?) AND level NOT IN ('INFO','DEBUG','TRACE') "
        "ORDER BY timestamp,filename,line",
        (start, end, filename, filename),
    )
    episodes = []
    groups = {}
    previous = last_key = None
    after_critical = False
    for file, line, stamp, level, logger, msg in events:
        moment = datetime.fromisoformat(stamp)
        critical = level in ("FATAL", "CRITICAL", "SEVERE")
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
            groups[key] = dict(
                level=level,
                logger=logger,
                message=msg[:200],
                count=0,
                ref=dict(filename=file, line=line),
            )
            episode["groups"].append(groups[key])
        elif key != last_key:
            episode["interleaved"] = True
        groups[key]["count"] += 1
        episode["last"] = stamp
        previous, last_key, after_critical = moment, key, critical
    result = dict(episodes=[], omitted_episodes=len(episodes))
    for episode in episodes:
        result["episodes"].append(episode)
        result["omitted_episodes"] -= 1
        episode["omitted_groups"] = 0
        while episode["groups"] and not fits(result):
            episode["groups"].pop()
            episode["omitted_groups"] += 1
        if not episode["groups"]:
            result["episodes"].pop()
            result["omitted_episodes"] += 1
            break
    return result


def nearby(db: SQLiteLogs, refs: list[dict], radius: int) -> dict[str, Any]:
    windows = []
    candidates = {}
    result = dict(rows=[], windows=windows, truncated=False)
    for ref in refs:
        file, line = ref["filename"], ref["line"]
        rows = list(
            db.connection.execute(
                f"SELECT {EVIDENCE_COLUMNS} FROM logs WHERE filename=? "
                "AND line BETWEEN ? AND ? ORDER BY line",
                (file, line - radius, line + radius),
            )
        )
        found = any(row[1] == line for row in rows)
        windows.append(dict(**ref, found=found, clipped=False))
        if found:
            for row in rows:
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
    result["rows"].sort()
    return result
