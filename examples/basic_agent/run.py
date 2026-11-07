from pathlib import Path
from typing import cast
from dotenv import load_dotenv

from openai.types.chat import ChatCompletionToolParam

from harness.prompts import PromptStore
from harness.enums import PromptFamily
from harness.llms import SyncTextLLMClient
from harness.logger import ApplicationLogger
from harness.tools import ToolRegistry
from .basic_agent import BasicAgent

# Importing tools registers them to the registry
import harness.builtin_tools # noqa: F401

load_dotenv()
root = Path(__file__).resolve().parent.parent

# Initialize both the registries (both are independent and not tied to a single agent)
PromptStore.initialize(root / "data" / "prompts.db")
ToolRegistry.initialize()

# Construct tool definitions to be given to the agent ( at any time you can change which tools the
# agent should get ). For a simple example we give it all the built in tools at every turn.
tools = cast(
    list[ChatCompletionToolParam], list(ToolRegistry.definitions().values())
)

logger = ApplicationLogger(root / "data", console=True)

# Initialize the agent
agent = BasicAgent(
    client=SyncTextLLMClient(),
    logger=logger,
    tools=tools,
    system_prompt=PromptStore.load_prompt(PromptFamily.SYSTEM)
)

# Keeping it inline with other examples we will give the following queries:
# This is just simulating the queries input by a user. If you want a chat like interface, simply use
# query = input().strip() in the loop below.
queries: list[str] = [
    "My project is called Atlas. It uses Spring Boot, PostgreSQL, and Docker. "
    "Remember these details.",
    "What's the weather in Patiala?",
    "I prefer concise answers. My project database is PostgreSQL, not MySQL.",
    "List the contents of /workspace/atlas.",
    "For Atlas, we decided to use Flyway for database migrations."
    "Keep that decision in mind.",
    "What was the project name, and which database and migration tool did we choose?",
    "My second project is called Orion. It uses C++ and gRPC. Don't confuse it with Atlas.",
    "What's the weather in Jaipur?",
    "Summarize the technical decisions we've made for Atlas and Orion.",
    "What was the weather location I asked about first?",
    "exit",
]

try:
    for query in queries:
        
        if query.lower() in ("exit", "quit"):
            break

        if not query:
            continue

        with agent.turn():
            agent.add_user_message(query)

            # step returns whether current turn should continue or not
            # you can add extra (in between turn) logic here, like determining
            # if the agent is in correct direction or not etc. or in a
            # master agent governing a sub agent secanrio.
            while agent.step():

                # For this simple example we do nothing.
                pass

finally:
    logger.close()
