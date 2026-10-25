from ..tools import BaseTool, ToolRegistry
from typing import Any

@ToolRegistry.register
class list_directory(BaseTool):
    name = "list_directory"
    description = "List the contents of a directory."

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The directory path to list.",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "path": args["path"],
            "entries": ["main.py", "helpers.py", "constants.py"],
        }