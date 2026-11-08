import pytest
from unittest.mock import Mock

from harness.tools import ToolRegistry
from harness.builtin_tools.dummy_tools import list_directory, WeatherTool

def test_whether_builtin_tools_registered() -> None:
    definitions = ToolRegistry.class_definitions()

    for tool in (list_directory, WeatherTool):
        assert definitions[tool.name] == {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "strict": True,
            },
        }

def test_empty_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ToolRegistry, "_tool_classes", {})
    assert ToolRegistry.class_definitions() == {}

def test_register_returns_original_class(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ToolRegistry, "_tool_classes", {})

    assert ToolRegistry.register(WeatherTool) is WeatherTool
    assert ToolRegistry.class_definitions() == {WeatherTool.name: WeatherTool.definition()}

def test_duplicate_registration_preserves_original() -> None:
    definitions = ToolRegistry.class_definitions()

    with pytest.raises(ValueError, match="Duplicate tool: get_weather"):
        ToolRegistry.register(WeatherTool)

    assert ToolRegistry.class_definitions() == definitions

def test_definitions_do_not_initialize_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    constructor = Mock(side_effect=AssertionError("Definitions must not construct tools."))
    monkeypatch.setattr(WeatherTool, "__init__", constructor)

    assert ToolRegistry.class_definitions()[WeatherTool.name] == WeatherTool.definition()
    constructor.assert_not_called()
