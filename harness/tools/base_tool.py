from abc import ABC, abstractmethod
from typing import Any

class BaseTool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]

    @abstractmethod
    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        """ Executes the tool. """
        ...

    @classmethod
    def definition(cls) -> dict[str, Any]:
        """ Returns the tool definition based on OpenAI Format. """

        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": cls.description,
                "parameters": cls.parameters,
                "strict": True,
            },
        }