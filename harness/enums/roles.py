from enum import Enum

class MessageRole(Enum):
    system    = "system"
    user      = "user"
    developer = "developer"
    assistant = "assistant"
    tool      = "tool"