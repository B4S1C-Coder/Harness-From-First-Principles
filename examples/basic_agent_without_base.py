# Register tools (importing them, registers them)
import harness.builtin_tools # noqa: F401
import json

from dotenv import load_dotenv
from pathlib import Path
from collections.abc import Callable
from harness.prompts import PromptStore
from harness.tools import ToolRegistry
from harness.llms import SyncTextLLMClient
from harness.compaction import naive_compaction
from harness.logger import ApplicationLogger
from harness.enums import PromptFamily
from harness.exceptions import ApplicationException, UnexpectedResponseError
from typing import cast
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
    ChatCompletionMessageFunctionToolCall,
)

load_dotenv()

ROOT = Path(__file__).resolve().parent
MAX_TURNS_PER_QUERY = 3
CONTEXT_BUDGET = 8_000
COMPACTION_THRESHOLD = 0.10
RECENT_TURNS_TO_KEEP = 2

# It is assumed prompts are already registered
PromptStore.initialize(ROOT / "data" / "prompts.db")
ToolRegistry.initialize()

def query_source(func: Callable[[], str]) -> Callable[[], str]:
    return func

def step(
    client: SyncTextLLMClient,
    logger: ApplicationLogger,
    messages: list[ChatCompletionMessageParam],
    tools: list[ChatCompletionToolParam],
    user_query: str
) -> list[ChatCompletionMessageParam]:

    if not user_query:
        return messages

    messages.append({
        "role": "user",
        "content": user_query
    })

    for _ in range(MAX_TURNS_PER_QUERY):
        logger.debug("Query sent to model.")

        response, input_tokens, cached_tokens = client.generate_next(
            cast(list[ChatCompletionToolParam], tools),
            cast(list[ChatCompletionMessageParam], messages)
        )

        logger.info(f"Input tok: {input_tokens}, Cached tok: {cached_tokens}")

        assistant_message = response.choices[0].message

        # Handle any tool calls
        if assistant_message.tool_calls:
            logger.debug("Executing tool calls ...")

            messages.append(
                cast(
                    ChatCompletionMessageParam,
                    assistant_message.model_dump(exclude_none=True)
                )
            )

            for tool_call in assistant_message.tool_calls:
                if not isinstance(tool_call, ChatCompletionMessageFunctionToolCall):
                    logger.warning("Potentially malformed tool call skipped")
                    continue

                logger.debug(f"Executing tool call: {tool_call.function.name}")

                result = ToolRegistry.execute(
                    tool_call.function.name,
                    json.loads(tool_call.function.arguments)
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                })

            continue

        llm_reply = assistant_message.content

        if not llm_reply:
            raise UnexpectedResponseError("LLM Provider")

        print(f"LLM Reply> {llm_reply}")

        messages.append({
            "role": "assistant",
            "content": llm_reply,
        })

        if input_tokens >= CONTEXT_BUDGET * COMPACTION_THRESHOLD:
            messages = naive_compaction(
                cast(list[ChatCompletionMessageParam], messages),
                client,
                RECENT_TURNS_TO_KEEP
            )
        break
    else:
        logger.warning("Maximum turns reached for this call")

    return messages

def loop(
    queries: list[str]
) -> None:

    messages: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": PromptStore.load_prompt(PromptFamily.SYSTEM),
        },
    ]

    tools = cast(
        list[ChatCompletionToolParam],
        list(ToolRegistry.definitions().values())
    )

    client = SyncTextLLMClient()
    logger = ApplicationLogger(ROOT / "data", console=True)

    query_iter = iter(queries)

    while True:
        with logger.correlation_scope():
            try:
                user_query = next(query_iter, "exit").strip()

                if user_query.lower() in ("exit", "quit"):
                    break

                messages = step(client, logger, messages, tools, user_query)                

            except ApplicationException as exc:
                logger.log_exception(exc.message, exc)

if __name__ == "__main__":
    loop([
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
    ])