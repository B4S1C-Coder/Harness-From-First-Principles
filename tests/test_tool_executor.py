import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from jsonschema import SchemaError

from harness import exceptions
from harness.logger import ApplicationLogger
from harness.tools import ToolRegistry, ToolExecutor, ToolExecutionLimits
from harness.builtin_tools.dummy_tools import list_directory, WeatherTool

def test_empty_executor(app_logger: ApplicationLogger) -> None:
    executor = ToolExecutor(app_logger, [])

    assert executor.definitions() == {}
    assert json.loads(executor.execute("missing", {})) == {
        "success": False, "error": "Tool not available: missing",
    }

def test_unregistered_tool_is_rejected(
    monkeypatch: pytest.MonkeyPatch, app_logger: ApplicationLogger,
) -> None:
    monkeypatch.setattr(ToolRegistry, "_tool_classes", {})

    with pytest.raises(exceptions.UnregisteredToolError, match="Unregistered tool: get_weather"):
        ToolExecutor(app_logger, [WeatherTool()])

def test_duplicate_tool_is_rejected(app_logger: ApplicationLogger) -> None:
    with pytest.raises(exceptions.DuplicateToolError, match="Duplicate tool: get_weather"):
        ToolExecutor(app_logger, [WeatherTool(), WeatherTool()])

def test_invalid_schema_is_rejected(
    monkeypatch: pytest.MonkeyPatch, app_logger: ApplicationLogger,
) -> None:
    monkeypatch.setattr(WeatherTool, "parameters", {"type": "invalid"})

    with pytest.raises(SchemaError):
        ToolExecutor(app_logger, [WeatherTool()])

def test_only_bound_tools_are_available(tool_executor: ToolExecutor) -> None:
    assert tool_executor.definitions() == {WeatherTool.name: WeatherTool.definition()}
    assert json.loads(tool_executor.execute(list_directory.name, {"path": "."})) == {
        "success": False, "error": "Tool not available: list_directory",
    }
    assert json.loads(tool_executor.execute(WeatherTool.name, {"location": "Delhi"})) == {
        "success": True,
        "data": {"location": "Delhi", "temperature_celsius": 28, "condition": "Sunny"},
    }

def test_executors_have_independent_tool_instances(
    monkeypatch: pytest.MonkeyPatch, app_logger: ApplicationLogger,
) -> None:
    first_tool, second_tool = WeatherTool(), WeatherTool()
    first_driver = Mock(return_value={"agent": "first"})
    second_driver = Mock(return_value={"agent": "second"})
    monkeypatch.setattr(first_tool, "driver", first_driver)
    monkeypatch.setattr(second_tool, "driver", second_driver)
    first = ToolExecutor(app_logger, [first_tool])
    second = ToolExecutor(app_logger, [second_tool])

    assert first.definitions() == second.definitions()
    assert json.loads(first.execute(WeatherTool.name, {"location": "Delhi"})) == {
        "success": True, "data": {"agent": "first"},
    }
    second_driver.assert_not_called()
    assert json.loads(second.execute(WeatherTool.name, {"location": "Mumbai"})) == {
        "success": True, "data": {"agent": "second"},
    }
    first_driver.assert_called_once_with({"location": "Delhi"})
    second_driver.assert_called_once_with({"location": "Mumbai"})

@pytest.mark.parametrize(("args", "error"), [
    (None, "Tool arguments must be a JSON object."),
    ([], "Tool arguments must be a JSON object."),
    ("location", "Tool arguments must be a JSON object."),
    ({"location": object()}, "Tool arguments must be JSON-serializable."),
    ({"location": float("nan")}, "Tool arguments must be JSON-serializable."),
    ({"location": float("inf")}, "Tool arguments must be JSON-serializable."),
    ({}, "Invalid arguments:"),
    ({"location": 1}, "Invalid arguments:"),
    ({"location": "ok", "extra": True}, "Invalid arguments:"),
])
def test_invalid_arguments_do_not_execute_tool(
    tool_executor: ToolExecutor, monkeypatch: pytest.MonkeyPatch, args: Any, error: str,
) -> None:
    driver = Mock()
    monkeypatch.setattr(WeatherTool, "driver", driver)
    response = json.loads(tool_executor.execute(WeatherTool.name, args))

    assert response["success"] is False
    assert response["error"].startswith(error)
    driver.assert_not_called()

def test_default_execution_limits() -> None:
    limits = ToolExecutionLimits()
    assert limits.max_argument_bytes == 64 * 1024
    assert limits.max_result_bytes == 128 * 1024

@pytest.mark.parametrize(("argument_bytes", "result_bytes"), [
    (0, 128), (-1, 128), (128, 0), (128, -1),
])
def test_execution_limits_must_be_positive(argument_bytes: int, result_bytes: int) -> None:
    with pytest.raises(ValueError, match="Tool execution limits must be positive"):
        ToolExecutionLimits(argument_bytes, result_bytes)

@pytest.mark.parametrize("extra_bytes", [-1, 0, 1])
def test_argument_size_boundary(
    monkeypatch: pytest.MonkeyPatch, app_logger: ApplicationLogger, extra_bytes: int,
) -> None:
    driver = Mock(return_value={"condition": "Sunny"})
    monkeypatch.setattr(WeatherTool, "driver", driver)
    args = {"location": "é🌧"}
    size = len(json.dumps(args, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    executor = ToolExecutor(
        app_logger, [WeatherTool()],
        limits=ToolExecutionLimits(max_argument_bytes=size + extra_bytes),
    )

    response = json.loads(executor.execute(WeatherTool.name, args))

    if extra_bytes < 0:
        assert response == {
            "success": False, "error": "Tool arguments exceed maximum allowed size",
        }
        driver.assert_not_called()
    else:
        assert response == {"success": True, "data": driver.return_value}
        driver.assert_called_once_with(args)

@pytest.mark.parametrize("extra_bytes", [-1, 0, 1])
def test_result_size_boundary(
    monkeypatch: pytest.MonkeyPatch, app_logger: ApplicationLogger, extra_bytes: int,
) -> None:
    result = {"location": "é🌧" * 32}
    driver = Mock(return_value=result)
    monkeypatch.setattr(WeatherTool, "driver", driver)
    expected = {"success": True, "data": result}
    size = len(json.dumps(expected, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    executor = ToolExecutor(
        app_logger, [WeatherTool()],
        limits=ToolExecutionLimits(max_result_bytes=size + extra_bytes),
    )

    response = json.loads(executor.execute(WeatherTool.name, {"location": "ok"}))

    if extra_bytes < 0:
        assert response == {
            "success": False, "error": "Tool result exceeds maximum allowed size.",
        }
    else:
        assert response == expected
    driver.assert_called_once_with({"location": "ok"})

@pytest.mark.parametrize(("error", "message", "log_message"), [
    (exceptions.ToolExecutionError("Application failure"),
     "Application failure", "Application failure"),
    (FileNotFoundError("Missing file"), "Missing file", "Unclassified OS, File, Unicode error"),
    (FileExistsError("Existing file"), "Existing file", "Unclassified OS, File, Unicode error"),
    (NotADirectoryError("Not a directory"),
     "Not a directory", "Unclassified OS, File, Unicode error"),
    (IsADirectoryError("Is a directory"), "Is a directory", "Unclassified OS, File, Unicode error"),
    (PermissionError("Access denied"), "Access denied", "Unclassified OS, File, Unicode error"),
    (UnicodeError("Invalid text"), "Invalid text", "Unclassified OS, File, Unicode error"),
    (OSError("OS failure"), "OS failure", "Unclassified OS, File, Unicode error"),
    (ValueError("Invalid value"), "Invalid value", "Unclassified OS, File, Unicode error"),
    (RuntimeError("Private details"),
     "Internal tool execution error.", "Unexpected error during tool execution"),
])
def test_execution_errors_are_returned_and_logged(
    tool_executor: ToolExecutor, monkeypatch: pytest.MonkeyPatch, app_logger: ApplicationLogger,
    log_dir: Path, error: Exception, message: str, log_message: str,
) -> None:
    driver = Mock(side_effect=error)
    monkeypatch.setattr(WeatherTool, "driver", driver)

    assert json.loads(tool_executor.execute(WeatherTool.name, {"location": "ok"})) == {
        "success": False, "error": message,
    }
    driver.assert_called_once_with({"location": "ok"})

    app_logger.close()
    application_log = (log_dir / "application.log").read_text(encoding="utf-8")
    trace_log = (log_dir / "traces.log").read_text(encoding="utf-8")

    for content in (application_log, trace_log):
        assert log_message in content
        assert type(error).__name__ in content
        assert str(error) in content
    assert "Traceback (most recent call last)" in trace_log

@pytest.mark.parametrize(("result", "message", "log_message"), [
    ({"location": object()},
     "Internal tool execution error.", "Unexpected error during tool execution"),
    ({"location": float("nan")}, "Out of range float values are not JSON compliant",
     "Unclassified OS, File, Unicode error"),
])
def test_unserializable_results_are_returned_as_errors(
    tool_executor: ToolExecutor, monkeypatch: pytest.MonkeyPatch, app_logger: ApplicationLogger,
    log_dir: Path, result: Any, message: str, log_message: str,
) -> None:
    monkeypatch.setattr(WeatherTool, "driver", Mock(return_value=result))

    response = json.loads(tool_executor.execute(WeatherTool.name, {"location": "ok"}))

    assert response["success"] is False
    assert response["error"].startswith(message)
    app_logger.close()
    assert log_message in (log_dir / "application.log").read_text(encoding="utf-8")
