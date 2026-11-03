from enum import StrEnum

class PromptFamily(StrEnum):
    SYSTEM     = "system"
    COMPACTION = "compaction"
    GUARDRAILS = "guardrails"