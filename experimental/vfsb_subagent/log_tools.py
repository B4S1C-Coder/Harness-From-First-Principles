"""Bounded log investigation tools for this experiment."""

import json
from dataclasses import asdict
from typing import Any

from . import log_evidence
from .log_pivots import MAX_PIVOTS
from harness.tools import BaseTool, ToolRegistry
from experimental.vfsb_subagent.log_backend import SEARCH_BYTES, SQLiteLogs
from experimental.vfsb_subagent.query_helper import QueryHelper


@ToolRegistry.register
class LogOverviewTool(BaseTool):
    name = "log_overview"
    description = "Summarize log counts and time ranges by file and level. Results are bounded."
    # Groq can treat an empty properties map as missing when required is present.
    # Omitting the empty required list preserves the zero-argument schema.
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}

    def __init__(self, backend: SQLiteLogs) -> None:
        self.backend = backend

    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        return asdict(self.backend.overview())


@ToolRegistry.register
class SearchLogsTool(LogOverviewTool):
    name = "search_logs"
    description = (
        "Batch independent searches in one call. Each query uses inclusive times, exact file "
        "and level, and a case-sensitive literal keyword. Null disables a filter. Results "
        "follow query order. One query returns rows directly. Up to 20 rows each, 5 KiB total. "
        "total_matches is the full count, so do not search just to count."
    )
    query_schema = {
        "type": "object",
        "properties": {
            key: {"type": ["string", "null"]}
            for key in ("start", "end", "level", "filename", "keyword")
        },
        "required": ["start", "end", "level", "filename", "keyword"],
        "additionalProperties": False,
    }

    parameters = {
        "type": "object",
        "properties": {
            "queries": {"type": "array", "items": query_schema, "minItems": 1, "maxItems": 8}
        },
        "required": ["queries"],
        "additionalProperties": False,
    }

    def driver(self, args: dict[str, Any]) -> dict:
        matches = [self.backend.search(**query) for query in args["queries"]]
        totals = [self.backend.count_matches(**query) for query in args["queries"]]
        if len(matches) == 1:
            return {**asdict(matches[0]), "total_matches": totals[0]}
        groups = [
            {"rows": [], "truncated": match.truncated, "total_matches": total}
            for match, total in zip(matches, totals, strict=True)
        ]
        response = {"columns": matches[0].columns, "results": groups}
        # Allocate one row per query per round, preserving each query's chronological prefix.
        for index in range(max(len(match.rows) for match in matches)):
            for match, group in zip(matches, groups, strict=True):
                if index >= len(match.rows) or len(group["rows"]) != index:
                    continue
                group["rows"].append(match.rows[index])
                if len(json.dumps(response).encode()) > SEARCH_BYTES - 128:
                    group["rows"].pop()
                    group["truncated"] = True
        return response


@ToolRegistry.register
class NearbyLogsTool(LogOverviewTool):
    name = "nearby_logs"
    description = (
        "Batch source context. Row columns: filename, line, timestamp, level, logger, message."
    )
    parameters = {
        "type": "object",
        "properties": {
            "refs": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_PIVOTS,
                "items": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "maxLength": 255},
                        "line": {"type": "integer", "minimum": 1},
                    },
                    "required": ["filename", "line"],
                    "additionalProperties": False,
                },
            },
            "radius": {"type": "integer", "minimum": 0, "maximum": 9},
        },
        "required": ["refs", "radius"],
        "additionalProperties": False,
    }

    def driver(self, args: dict[str, Any]) -> dict:
        return log_evidence.nearby(self.backend, **args)


@ToolRegistry.register
class ScanSignaturesTool(LogOverviewTool):
    name = "scan_signatures"
    description = (
        "Count lines per failure signature; zero-count names are listed under zero. Pass "
        "custom=[] for the built-in catalog. A custom entry is ONE mechanism: its alternatives "
        "are spellings of the same message (case-insensitive literals), not different "
        "hypotheses, and each alternative's count is returned. Never combine mechanisms."
    )
    parameters = {
        "type": "object",
        "properties": {
            "custom": {
                "type": "array",
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "minLength": 1, "maxLength": 32},
                        "alternatives": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 8,
                            "items": {"type": "string", "minLength": 1, "maxLength": 128},
                        },
                    },
                    "required": ["name", "alternatives"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["custom"],
        "additionalProperties": False,
    }

    def driver(self, args: dict[str, Any]) -> dict:
        return log_evidence.scan(self.backend, args["custom"])


@ToolRegistry.register
class TimelineTool(LogOverviewTool):
    name = "timeline"
    description = (
        "Ordered warning and failure episodes (non-INFO) with per-group count and first/last "
        "timestamp within the episode, ref file:line and message. Null start/end/filename mean "
        "no limit. A message type already shown is shortened in later episodes. If groups or "
        "episodes are omitted (lowest severity first), narrow the window or re-run with "
        "start=next_start."
    )
    parameters = {
        "type": "object",
        "properties": {
            "start": {"type": ["string", "null"]},
            "end": {"type": ["string", "null"]},
            "filename": {"type": ["string", "null"]},
        },
        "required": ["start", "end", "filename"],
        "additionalProperties": False,
    }

    def driver(self, args: dict[str, Any]) -> dict:
        return log_evidence.timeline(self.backend, **args)


@ToolRegistry.register
class AdvancedLogAnalysisTool(BaseTool):
    name = "advanced_log_analysis"
    description = (
        "Ask a focused natural-language aggregation or correlation questio"
        "n that deterministic search cannot answer. Returns successful SQL"
        " and bounded results."
    )
    parameters = {
        "type": "object",
        "properties": {"request": {"type": "string", "maxLength": 2000}},
        "required": ["request"],
        "additionalProperties": False,
    }

    def __init__(self, helper: QueryHelper) -> None:
        self.helper = helper

    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.helper.analyze(args["request"])


@ToolRegistry.register
class IncidentDigestTool(BaseTool):
    name = "incident_digest"
    description = (
        "Narrow the opening digest: non-INFO lines grouped into message types "
        "(numbers, ids, IPs ignored when grouping). Returns corpus size and time range, line "
        "counts by level, and per group: count, files, first/last timestamp, first_ref "
        "(file:line, for nearby_logs) and message (verbatim text of the FIRST occurrence; later "
        "ones may differ in numbers, ids or hosts). Rows are in order of first appearance; "
        "counts show volume, not causality. If groups were omitted, narrow with "
        "start/end/filename or level. Null disables a filter."
    )
    parameters = {
        "type": "object",
        "properties": {
            key: {"type": ["string", "null"]} for key in ("start", "end", "level", "filename")
        },
        "required": ["start", "end", "level", "filename"],
        "additionalProperties": False,
    }

    def __init__(self, backend: SQLiteLogs) -> None:
        self.backend = backend

    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.backend.digest(**args)
