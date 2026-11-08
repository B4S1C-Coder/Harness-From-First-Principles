from pathlib import Path
from dotenv import load_dotenv

from harness.prompts import PromptStore
from harness.enums import PromptFamily
from harness.llms import SyncTextLLMClient
from harness.logger import ApplicationLogger
from harness.tools import ToolRegistry

from .fs_agent import FileSystemAgent

load_dotenv()
root = Path(__file__).resolve().parent.parent
workspace_root = root / "data" / "workspace"

PromptStore.initialize(root / "data" / "prompts.db")
# ToolRegistry.initialize()

logger = ApplicationLogger(root / "data", console=True)

agent = FileSystemAgent(
    root=workspace_root,
    client=SyncTextLLMClient(),
    logger=logger,
    system_prompt=PromptStore.load_prompt(PromptFamily.SYSTEM),
    compaction_threshold=0.8,
    recent_turns_to_keep=4
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
