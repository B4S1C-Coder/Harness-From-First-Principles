import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
from ..logger import ApplicationLogger
from .. import exceptions
from . import BaseTool, ToolRegistry

@dataclass(frozen=True)
class ToolExecutionLimits:
    max_argument_bytes: int = 64 * 1024
    max_result_bytes: int = 128 * 1024

    def __post_init__(self) -> None:
        if self.max_argument_bytes <= 0 or self.max_result_bytes <= 0:
            raise ValueError("Tool execution limits must be positive.")

class ToolExecutor:
    def __init__(
        self,
        logger: ApplicationLogger,
        tools: Iterable[BaseTool],
        *,
        limits: ToolExecutionLimits | None = None
    ) -> None:

        self._tools: dict[str, BaseTool] = {}
        self._validators: dict[str, Draft202012Validator] = {}
        self._definitions: dict[str, dict[str, Any]] = {}
        self._limits = limits or ToolExecutionLimits()
        self._logger = logger

        registered = ToolRegistry.class_definitions()

        # seems unncessary, since these classes are controlled by the programmer, it is what it is
        for tool in tools:
            name = tool.name

            if name not in registered:
                raise exceptions.UnregisteredToolError(name)

            if name in self._tools:
                raise exceptions.DuplicateToolError(name)

            schema = tool.parameters
            Draft202012Validator.check_schema(schema)

            self._tools[name] = tool
            self._validators[name] = Draft202012Validator(schema)
            self._definitions[name] = registered[name]

    def definitions(self) -> dict[str, dict[str, Any]]:
        """ Returns definitions for tools bound to this executor. """
        return self._definitions

    def _response(self, *, success: bool, data: Any = None, error: str | None = None) -> str:
        """ Build a bounded JSON Response """

        response: dict[str, Any] = { "success": success }

        if success:
            response["data"] = data
        else:
            response["error"] = error

        encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False)

        parts: list[str] = []
        total_bytes = 0

        for part in encoder.iterencode(response):
            total_bytes += len(part.encode("utf-8"))

            if total_bytes > self._limits.max_result_bytes:
                return json.dumps({
                    "success": False,
                    "error": "Tool result exceeds maximum allowed size."
                })

            parts.append(part)

        return "".join(parts)

    def execute(self, name: str, args: dict[str, Any]) -> str:
        """ Validate and execute an explicitly bound tool. """

        if name not in self._tools:
            return self._response(success=False, error=f"Tool not available: {name}")

        if not isinstance(args, dict):
            return self._response(success=False, error="Tool arguments must be a JSON object.")

        try:
            encoded_args = json.dumps(args, ensure_ascii=False, allow_nan=False).encode("utf-8")

        except (TypeError, ValueError):
            return self._response(success=False, error="Tool arguments must be JSON-serializable.")

        if len(encoded_args) > self._limits.max_argument_bytes:
            return self._response(success=False, error="Tool arguments exceed maximum allowed size")

        try:
            self._validators[name].validate(args)
        
        except ValidationError as exc:
            return self._response(success=False, error=f"Invalid arguments: {exc.message}")

        tool = self._tools[name]

        try:
            result = tool.driver(args)
            return self._response(success=True, data=result)

        # probably way too defensive
        except exceptions.ApplicationException as exc:
            self._logger.log_exception(exc.message, exc)
            return self._response(success=False, error=exc.message)

        except (
            FileNotFoundError,
            FileExistsError,
            NotADirectoryError,
            IsADirectoryError,
            PermissionError,
            UnicodeError,
            OSError,
            ValueError,
        ) as exc:
            self._logger.log_exception("Unclassified OS, File, Unicode error", exc)
            return self._response(success=False, error=str(exc))

        except Exception as exc:
            self._logger.log_exception(
                "Unexpected error during tool execution", exc, include_trace=True
            )
            return self._response(success=False, error="Internal tool execution error.")
