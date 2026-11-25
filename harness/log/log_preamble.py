"""Collect and fit the opening evidence for one investigation conversation."""

import json
from collections.abc import Callable, Iterator
from copy import deepcopy
from dataclasses import asdict
from typing import Any

from harness.exceptions import ToolExecutionError, UnexpectedResponseError
from harness.tools import ToolExecutor
from .log_backend import SQLiteLogs
from .log_digest import SEVERITY, normalize
from .log_evidence import REPEAT_MESSAGE_CHARS
from .log_pivots import select_pivots

DEFAULT_CALLS = {
    "incident_digest": dict.fromkeys(("start", "end", "level", "filename")),
    "scan_signatures": {"custom": []},
    "timeline": dict.fromkeys(("start", "end", "filename")),
}
PACK_PREFIX = "Opening log evidence (source data):\n"
type Payload = dict[str, Any]


def _retrieve(executor: ToolExecutor, name: str, args: Payload) -> Payload:
    response = json.loads(executor.execute(name, args))
    if response["success"]:
        return response["data"]
    return {"unavailable": response["error"]}


def collect(db: SQLiteLogs, executor: ToolExecutor) -> Payload:
    pack = {name: _retrieve(executor, name, args) for name, args in DEFAULT_CALLS.items()}
    try:
        pivots, omitted = select_pivots(db)
    except ToolExecutionError as exc:
        pack["nearby_logs"] = {"unavailable": str(exc)}
        return pack

    nearby: Payload = {"rows": [], "truncated": False}
    if pivots:
        refs = [{"filename": pivot.filename, "line": pivot.line} for pivot in pivots]
        nearby = _retrieve(executor, "nearby_logs", {"refs": refs, "radius": 1})
    windows = nearby.pop("windows", [])
    nearby["pivots"] = [asdict(pivot) for pivot in pivots]
    for pivot, window in zip(nearby["pivots"], windows, strict=False):
        pivot.update(window)
    nearby["omitted_error_families"] = omitted
    nearby["columns"] = ["filename", "line", "timestamp", "level", "logger", "message"]
    pack["nearby_logs"] = nearby
    return pack


def _render(pack: Payload) -> str:
    # Rebuild links after each cut so a retained row never points to an omitted excerpt.
    view = deepcopy(pack)
    excerpts = {
        (f"{file}:{line}", message): "nearby_logs"
        for file, line, _, _, _, message in view["nearby_logs"].get("rows", [])
    }
    digest = view["incident_digest"].get("rows", [])
    episodes = view["timeline"].get("episodes", [])
    for name, rows in (
        ("incident_digest", digest),
        ("timeline", (row for episode in episodes for row in episode["groups"])),
    ):
        for row in rows:
            ref, message = row[-2:]
            source = excerpts.setdefault((ref, message), name)
            if source != name and len(message) > len(source) + 10:
                row[-1] = {"see": source}
    return PACK_PREFIX + json.dumps(view, ensure_ascii=False, separators=(",", ":"))


def _trim(pack: Payload) -> Iterator[str]:
    """Yield the affected section after each cut, from least to most costly to evidence."""
    nearby = pack["nearby_logs"]
    pivots = nearby.get("pivots", [])
    anchors = {(pivot["filename"], pivot["line"]) for pivot in pivots}
    rows = nearby.get("rows", [])
    for row in reversed(rows.copy()):
        file, line = row[:2]
        if (file, line) not in anchors:
            rows.remove(row)
            nearby["truncated"] = True
            for pivot in pivots:
                if file == pivot["filename"] and abs(line - pivot["line"]) <= 1:
                    pivot["clipped"] = True
            nearby["pack_omitted_rows"] = nearby.get("pack_omitted_rows", 0) + 1
            yield "nearby_logs"

    # Drop repeated timeline detail first, then lowest severity, latest first on ties.
    candidates = []
    seen = set()
    for episode in pack["timeline"].get("episodes", []):
        for row in episode["groups"]:
            key = (row[0], row[1], normalize(row[-1][:REPEAT_MESSAGE_CHARS]))
            candidates.append((key not in seen, row, "timeline", episode["groups"]))
            seen.add(key)
    digest = pack["incident_digest"].get("rows", [])
    candidates.extend((True, row, "incident_digest", digest) for row in digest)
    candidates.sort(key=lambda item: item[1][-4], reverse=True)  # first occurrence
    candidates.sort(key=lambda item: (item[0], SEVERITY.get(item[1][0].upper(), 1)))
    for _, row, name, group in candidates:
        group.remove(row)
        pack[name]["pack_omitted_rows"] = pack[name].get("pack_omitted_rows", 0) + 1
        yield name

    # Exceptionally little space may remain after a long question. Keep section status
    # and the pivot list even if only counts fit.
    for name in ("timeline", "scan_signatures", "incident_digest", "nearby_logs"):
        section = pack[name]
        if "unavailable" in section:
            continue
        if name == "nearby_logs":
            if not rows:
                continue
            section["pack_omitted_rows"] = section.get("pack_omitted_rows", 0) + len(rows)
            rows.clear()
            nearby["truncated"] = True
            for pivot in pivots:
                pivot["clipped"] = True
        else:
            summary = {"pack_omitted_rows": section.get("pack_omitted_rows", 0)}
            if name == "scan_signatures":
                summary["omitted_signatures"] = len(section["signatures"]) + len(section["zero"])
            elif name == "timeline":
                summary["omitted_episodes"] = len(section["episodes"]) + section["omitted_episodes"]
            else:
                summary["corpus_lines"] = section["corpus"]["lines"]
                summary["omitted_templates"] = section["scope"]["templates"]
            pack[name] = summary
        yield name


def fit(
    pack: Payload, estimate: Callable[[str], int], threshold: float
) -> tuple[str, set[str], int]:
    """Fit against the same full-request estimate used by the agent's first step."""
    complete = {name for name in DEFAULT_CALLS if "unavailable" not in pack[name]}
    cuts = _trim(pack)
    while True:
        content = _render(pack)
        tokens = estimate(content)
        if tokens < threshold:
            return content, complete, tokens
        section = next(cuts, None)
        if section is None:
            raise UnexpectedResponseError(
                "Investigation",
                "Question and minimum opening evidence exceed the context threshold.",
            )
        complete.discard(section)
