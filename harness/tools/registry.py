from typing import Any
from . import BaseTool

class ToolRegistry:
    _tool_classes: dict[str, type[BaseTool]] = {}
    _instances: dict[str, BaseTool] | None = None

    @classmethod
    def register[T: BaseTool](cls, tool_cls: type[T]) -> type[T]:
        """
        Decorator to register tools to the registry. Simply importing the tool would trigger it's
        registry. It's advisable to group tool imports in files and simply import that file.
        """
        name = tool_cls.name

        if name in cls._tool_classes:
            raise ValueError(f"Duplicate tool: {name}")
        
        cls._tool_classes[name] = tool_cls
        return tool_cls
    
    @classmethod
    def initialize(cls):
        """
        Initializes all the tool classes registered with the registry. The registry assumes eager
        initialization. If you need lazy initialization, then that must be implemented at the tool
        level outside of it's __init__() function.
        """
        # Already initialized
        if cls._instances is not None:
            return None
        
        cls._instances = {
            name: tool_cls()
            for name, tool_cls in cls._tool_classes.items()
        }
    
    @classmethod
    def execute(
        cls, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Executes the registered tool and returns the result. This method will raise errors in case
        of unkown tools or tool execution errors. So this method MUST BE IN A TRY EXCEPT block to
        avoid crashing the entire harness.
        """
        if not cls._instances:
            raise RuntimeError(
                "Registered tools have not been initialized. Call initialize() first."
            )

        try:
            tool = cls._instances[name]
        except KeyError:
            raise ValueError(f"Unkown tool: {name}") from None

        return tool.driver(arguments)
    
    @classmethod
    def definitions(cls) -> dict[str, dict[str, Any]]:
        """ Constructs the tool definitions of registered tools based on definition() method. """
        if not cls._instances:
            raise RuntimeError(
                "Registered tools have not been initialized. Call initialize() first."
            )
        
        return {
            name : tool.definition()
            for name, tool in cls._instances.items()
        }