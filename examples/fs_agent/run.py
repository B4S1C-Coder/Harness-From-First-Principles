from pathlib import Path
from dotenv import load_dotenv

from harness.prompts import PromptStore
from harness.enums import PromptFamily
from harness.llms import SyncTextLLMClient
from harness.logger import ApplicationLogger

from .fs_agent import FileSystemAgent, FSAgentConfig

load_dotenv()
root = Path(__file__).resolve().parent.parent
workspace_root = root / "data" / "workspace"

PromptStore.initialize(root / "data" / "prompts.db")

logger = ApplicationLogger(root / "data", console=True)

config = FSAgentConfig(
    root=workspace_root, readonly=False
)

agent = FileSystemAgent(
    client=SyncTextLLMClient(),
    logger=logger,
    system_prompt=PromptStore.load_prompt(PromptFamily.SYSTEM),
    compaction_threshold=0.8,
    recent_turns_to_keep=4,
    config=config
)

try:
    while True:

        query = input("User> ").strip()

        if query.lower() in ("exit", "quit"):
            break

        if not query:
            continue

        with agent.turn():
            agent.add_user_message(query)

            while agent.step():
                pass

finally:
    logger.close()
