"""Bounded log investigation tools for this experiment."""

from dataclasses import asdict
from typing import Any

from harness.tools import BaseTool, ToolRegistry
from experimental.vfsb_subagent.log_backend import SQLiteLogs
from experimental.vfsb_subagent.query_helper import QueryHelper


@ToolRegistry.register
class LogOverviewTool(BaseTool):
    name = "log_overview"
    description = "Summarize log counts and time ranges by file and level. Results are bounded."
    parameters = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}

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
    description = "Retrieve source lines around a 1-based line reference within one file."
    parameters = {
        "type": "object",
        "properties": {
            "filename": {"type": "string"},
            "line": {"type": "integer", "minimum": 1},
            "radius": {"type": "integer", "minimum": 0, "maximum": 9},
        },
        "required": ["filename", "line", "radius"],
        "additionalProperties": False,
    }

    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        return asdict(self.backend.nearby(**args))


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
