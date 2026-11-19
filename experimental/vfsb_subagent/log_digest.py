"""Deterministic incident digest: group WARN/ERROR lines by masked message template.

The digest gives an investigator a bounded map of *which kinds of failures exist, how often, and
when they first and last appeared* in one call. It involves no LLM. Pure functions live here so
they are testable without a database; `SQLiteLogs.digest` runs the SQL and feeds them.
"""

import json
import re
from functools import lru_cache
from typing import Any

# Serialized size budget for the digest payload (UTF-8 bytes, executor envelope excluded).
DIGEST_BYTES = 5000
# Reserved for the `omitted` block, which is added after rows are chosen.
_OMITTED_RESERVE = 260
MAX_MESSAGE_CHARS = 200
QUIET_LEVELS = ("INFO", "DEBUG", "TRACE")
SEVERITY = {"FATAL": 3, "CRITICAL": 3, "SEVERE": 3, "ERROR": 2}  # anything else ranks 1 (WARN, ...)
COLUMNS = ["level", "logger", "count", "files", "first", "last", "first_ref", "message"]

# Order matters: specific identifiers are masked before generic numbers.
_MASKS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), replacement)
    for pattern, replacement in (
        (r"\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d(?:[,.]\d+)?", "<TS>"),
        (r"\bBP-\d+-\d{1,3}(?:\.\d{1,3}){3}-\d+", "BP-<ID>"),
        (r"\b(attempt|appattempt|container|application|job|task)_\w+", r"\1_<ID>"),
        (r"\bblk_-?\d+(?:_\d+)?", "blk_<ID>"),
        # Loopback/wildcard addresses are diagnostic (e.g. a host resolving to 127.0.0.1), so they
        # are parked behind placeholders, restored after masking and exempt from <IP>.
        (r"\b127\.0\.0\.1\b", "@@LOOPBACK@@"),
        (r"\b0\.0\.0\.0\b", "@@WILDCARD@@"),
        (r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "<IP>"),
        (r"@[0-9a-fA-F]{4,}\b", "@<H>"),
        (r"\b0x[0-9a-fA-F]+\b|\b[0-9a-fA-F]{12,}\b", "<HEX>"),
        (r"(?<=_)\d+", "<N>"),
        # Numbers, but keep digits that belong to a hostname such as `node-41`.
        (r"(?<![A-Za-z]-)\b\d+(?:\.\d+)?", "<N>"),
        (r"\s+", " "),
    )
)


@lru_cache(maxsize=65536)
def _normalize(message: str) -> str:
    for pattern, replacement in _MASKS:
        message = pattern.sub(replacement, message)
    return message.replace("@@LOOPBACK@@", "127.0.0.1").replace("@@WILDCARD@@", "0.0.0.0").strip()


def normalize(message: str | None) -> str | None:
    """Mask volatile tokens (numbers, ids, IPs, timestamps) so similar messages group together."""
    return None if message is None else _normalize(message)


def _size(value: Any) -> int:
    # Same default separators as the tool executor's encoder, so budgets match the wire format.
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def _short_logger(name: str | None) -> str:
    return (name or "").rsplit(".", 1)[-1]


def _clip(text: str, limit: int = MAX_MESSAGE_CHARS) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_digest(
    corpus: dict[str, Any],
    scope: dict[str, Any],
    groups: list[tuple],
    *,
    byte_budget: int = DIGEST_BYTES,
    groups_capped: bool = False,
) -> dict[str, Any]:
    """Select the most informative template groups that fit the byte budget.

    `groups` rows are (level, logger, count, files, last_ts, first_blob), where first_blob is
    "timestamp<TAB>filename<TAB>zero-padded line<TAB>message" of the group's earliest occurrence.
    The template only defines the grouping; the row shows that occurrence's verbatim message, so
    nothing masked (e.g. `<IP>`) is ever presented as log text.

    Selection is by severity (FATAL > ERROR > the rest), then earliest first appearance, until the
    budget is used; the chosen rows are then presented in order of first appearance. Whatever did
    not fit is summarized under `omitted` so the caller can narrow the window or level.
    """
    parsed = []
    for level, logger, count, files, last, blob in groups:
        first, filename, line, message = blob.split("\t", 3)
        parsed.append(
            {
                "sev": SEVERITY.get((level or "").upper(), 1),
                "level": level,
                "row": [
                    level,
                    _short_logger(logger),
                    count,
                    files,
                    first,
                    last,
                    f"{filename}:{int(line)}",
                    _clip(message.strip()),
                ],
                "first": (first, filename, line),
            }
        )
    parsed.sort(key=lambda g: (-g["sev"], g["first"]))

    scope = {
        **scope,
        "templates": len(parsed),
        "lines_in_templates": sum(g["row"][2] for g in parsed),
    }
    if groups_capped:
        scope["template_groups_capped"] = True
    base = {"corpus": corpus, "scope": scope, "columns": COLUMNS, "rows": []}
    used = _size(base) + _OMITTED_RESERVE
    chosen: list[dict[str, Any]] = []
    for group in parsed:
        cost = _size(group["row"]) + 2  # ", " separator
        if used + cost > byte_budget:
            break
        used += cost
        chosen.append(group)

    skipped = parsed[len(chosen) :]
    chosen.sort(key=lambda g: g["first"])
    payload: dict[str, Any] = {**base, "rows": [g["row"] for g in chosen], "truncated": False}
    if skipped:
        by_level: dict[str, int] = {}
        for group in skipped:
            by_level[group["level"]] = by_level.get(group["level"], 0) + group["row"][2]
        payload["truncated"] = True
        payload["omitted"] = {
            "templates": len(skipped),
            "lines": sum(by_level.values()),
            "lines_by_level": by_level,
        }
    return payload
