from dotenv import load_dotenv
load_dotenv()

from pathlib import Path
from harness.prompts import PromptStore

PROMPTS_ROOT = Path(__file__).resolve().parent.parent.parent / "examples"
ROOT = Path(__file__).resolve().parent

MAIN_AGENT_SYSTEM_PROMPT = Path(ROOT / "system_main_agent.md").read_text()
SUB_AGENT_SYSTEM_PROMPT  = Path(ROOT / "system_sub_agent.md").read_text()

PromptStore.initialize(PROMPTS_ROOT / "data" / "prompts.db")
PromptStore.add_prompt("experimental.subagent.main.system", MAIN_AGENT_SYSTEM_PROMPT)
PromptStore.add_prompt("experimental.subagent.sub.system", SUB_AGENT_SYSTEM_PROMPT)
PromptStore.close()