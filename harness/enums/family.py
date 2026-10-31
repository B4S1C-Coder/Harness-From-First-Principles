from enum import Enum

class PromptFamily(Enum):
    SYSTEM     = "system"
    COMPACTION = "compaction"
    GUARDRAILS = "guardrails"