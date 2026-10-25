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
    
    def definition(self) -> dict[str, Any]:
        """ Returns the tool definition based on OpenAI Format. """

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
                "strict": True,
            },
        }