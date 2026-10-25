from ..tools import BaseTool, ToolRegistry
from typing import Any

@ToolRegistry.register
class WeatherTool(BaseTool):
    name = "get_weather"
    description = "Get the weather for a location."

    parameters = {
        "type": "object",
        "properties": {
            "location": {"type": "string"},
        },
        "required": ["location"],
        "additionalProperties": False,
    }

    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "location": args["location"],
            "temperature_celsius": 28,
            "condition": "Sunny",
        }