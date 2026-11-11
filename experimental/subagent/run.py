from dotenv import load_dotenv
from pathlib import Path
from harness.shortcuts.generic_scmt import SCMTTConfig, SCMTTAgent
from harness.llms import SyncTextLLMClient
from harness.logger import ApplicationLogger
from harness.prompts import PromptStore
from .hypothesis_agent import HypothesisReviewerAgent, ReviewHypothesisTool

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent.parent / "examples"
TOOL_CALL_PER_TURN_LIMIT = 3

PromptStore.initialize(ROOT / "data" / "prompts.db")
logger = ApplicationLogger(ROOT / "data", console=True)

sub_agent = HypothesisReviewerAgent(
    client=SyncTextLLMClient(model="openai/gpt-oss-20b"),
    logger=logger,
    system_prompt=PromptStore.load_prompt("experimental.subagent.sub.system"),
    compaction_threshold=0.8,
    recent_turns_to_keep=4
)

main_agent = SCMTTAgent(
    client=SyncTextLLMClient(model="openai/gpt-oss-120b"),
    logger=logger,
    system_prompt=PromptStore.load_prompt("experimental.subagent.main.system"),
    compaction_threshold=0.8,
    recent_turns_to_keep=4,
    config=SCMTTConfig(tools=(
        ReviewHypothesisTool(sub_agent),
    ))
)

try:
    while True:
        q = input("User> ").strip()

        if q.lower() in ("exit", "quit"):
            break

        if not q:
            continue

        with main_agent.turn():
            main_agent.add_user_message(q)
            remaining = TOOL_CALL_PER_TURN_LIMIT

            while remaining > 0 and main_agent.step():
                remaining -= 1

finally:
    logger.close()
    PromptStore.close()