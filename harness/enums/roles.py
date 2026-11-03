from enum import StrEnum

class MessageRole(StrEnum):
    system    = "system"
    user      = "user"
    developer = "developer"
    assistant = "assistant"
    tool      = "tool"