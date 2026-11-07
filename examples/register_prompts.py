from dotenv import load_dotenv
load_dotenv()

from pathlib import Path
from harness.prompts import PromptStore
from harness.enums import PromptFamily

ROOT = Path(__file__).resolve().parent

SYSTEM_PROMPT = """
You are a helpful assistant running inside a Python tool-calling harness.

Instructions:
1. Use tools whenever the user requests information that requires them.
2. Never invent tool results or claim a tool was executed when it wasn't.
3. If a request requires multiple tools, call all relevant tools.
4. After receiving tool results, interpret them and answer the user clearly.
5. If the user asks a general question that doesn't require a tool, answer directly.
6. If a tool returns an error, explain the error honestly.
7. Maintain conversation context across messages.
8. Be concise and do not expose internal implementation details unless asked.
"""

COMPACTION_PROMPT = """
Summarize the conversation history for future continuation.

Preserve important facts, user preferences, decisions, technical details,
relevant tool results, and unresolved tasks.

Distinguish verified results from assumptions. Do not invent information.
Be concise while preserving information needed for future responses.
Return only the summary.
"""

PromptStore.initialize(ROOT / "data" / "prompts.db")
PromptStore.add_prompt(PromptFamily.SYSTEM, SYSTEM_PROMPT)
# PromptStore.add_prompt(PromptFamily.COMPACTION, COMPACTION_PROMPT)
PromptStore.close()