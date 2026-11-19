"""Bounded log investigation tools for this experiment."""

from dataclasses import asdict
from typing import Any

from . import log_evidence
from harness.tools import BaseTool, ToolRegistry
from experimental.vfsb_subagent.log_backend import SQLiteLogs
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
        "Filter logs by inclusive timestamps, exact level/file and case-se"
        "nsitive literal keyword. Null disables a filter. At most 20 rows/"
        "4 KiB; narrow truncated searches."
    )
    parameters = {
        "type": "object",
        "properties": {
            key: {"type": ["string", "null"]}
            for key in ("start", "end", "level", "filename", "keyword")
        },
        "required": ["start", "end", "level", "filename", "keyword"],
        "additionalProperties": False,
    }

    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        return asdict(self.backend.search(**args))


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
                "maxItems": 8,
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
        "Count lines per signature, including zeros. Pass custom=[] for the built-in catalog. "
        "Custom signatures match any case-insensitive literal alternative."
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
        "Ordered warning and failure episodes within inclusive timestamps. "
        "Null filename includes all files."
    )
    parameters = {
        "type": "object",
        "properties": {
            "start": {"type": "string"},
            "end": {"type": "string"},
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
        "START HERE. Deterministic map of the logs: non-INFO lines grouped into message types "
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
