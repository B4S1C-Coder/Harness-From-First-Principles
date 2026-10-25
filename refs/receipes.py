import json
from collections.abc import Callable
from typing import cast

from constants import COMPACTION_PROMPT, EXIT_COMMANDS, SYSTEM_PROMPT
from dotenv import load_dotenv
from helpers import require_env
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessageFunctionToolCall,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)

load_dotenv()

# dummy tools
def get_weather(location: str) -> dict:
    """Dummy weather tool to test tool calling."""

    return {
        "location": location,
        "temperature_celsius": 28,
        "condition": "Sunny",
    }


def list_directory(path: str) -> dict:
    """Returns a dummy directory listing."""

    return {
        "path": path,
        "entries": ["main.py", "helpers.py", "constants.py"],
    }


# Tool definitions
TOOLS: list[ChatCompletionToolParam] = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city or location.",
                    }
                },
                "required": ["location"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List the contents of a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The directory path to list.",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
]

# Tool Dispatch

AVAILABLE_TOOLS = {
    "get_weather": get_weather,
    "list_directory": list_directory,
}


def execute_tool(name: str, arguments: str) -> str:
    """Execute a requested tool and return its result as JSON."""

    function = AVAILABLE_TOOLS.get(name)

    if function is None:
        return json.dumps({"error": f"Unknown tool: {name}"})

    try:
        parsed_arguments = json.loads(arguments)
        result = function(**parsed_arguments)
        return json.dumps(result)

    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return json.dumps({"error": str(exc)})


def compact_history(
    messages: list[ChatCompletionMessageParam],
    llm_client: OpenAI,
    model_name: str,
    recent_turns_to_keep: int,
) -> list[ChatCompletionMessageParam]:
    """Runs compaction to free up context window."""

    user_indices = [i for i, message in enumerate(messages) if message["role"] == "user"]

    if len(user_indices) <= recent_turns_to_keep:
        return messages

    # Start of the oldest user turn that needs to be preserved
    compact_until = user_indices[-recent_turns_to_keep]
    old_history = messages[1:compact_until]
    recent_history = messages[compact_until:]

    if not old_history:
        return messages

    response = llm_client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": COMPACTION_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    old_history,
                    ensure_ascii=False,
                ),
            },
        ],
    )

    summary = response.choices[0].message.content

    if not summary:
        return messages

    print("----------------")
    print("Harness> CONTEXT COMPACTED")
    print(summary)
    print("----------------")

    return [
        messages[0],
        {
            "role": "system",
            "content": ("Summary of earlier conversation:\n" + summary),
        },
        *recent_history,
    ]


QuerySupplier = Callable[[], str]


def query_source(func: QuerySupplier) -> QuerySupplier:
    return func


def agent_loop(llm_client: OpenAI, get_user_query: QuerySupplier):
    """Runs the main conversation loop."""

    messages: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    model_name = require_env("MODEL")
    MAX_TURNS_PER_QUERY = 3
    CONTEXT_BUDGET = 8_000
    COMPACTION_THRESHOLD = 0.10
    RECENT_TURNS_TO_KEEP = 2

    while True:
        user_query = get_user_query().strip()

        if user_query.lower() in EXIT_COMMANDS:
            break

        if not user_query:
            continue

        messages.append(
            {
                "role": "user",
                "content": user_query,
            }
        )

        for _ in range(MAX_TURNS_PER_QUERY):
            response = llm_client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )

            try:
                print("----")
                usage = response.usage

                if usage:
                    prompt_tokens = usage.prompt_tokens
                    details = usage.prompt_tokens_details
                    cached_tokens = details.cached_tokens if details else 0

                    print(f"Harness> Input Tok: {prompt_tokens}, Cached Tok: {cached_tokens}")

                    if cached_tokens:
                        print("Harness> Cache Hit")
                    else:
                        print("Harness> No cached tokens reported.")

                print("----")

            except Exception:
                print("Harness> No usage statistics.")

            assistant_message = response.choices[0].message

            # Handle any tool calls
            if assistant_message.tool_calls:
                print("Harness> Executing tools ...")

                messages.append(
                    cast(
                        ChatCompletionMessageParam,
                        assistant_message.model_dump(exclude_none=True),
                    )
                )

                # Execute tool calls
                for tool_call in assistant_message.tool_calls:
                    if not isinstance(tool_call, ChatCompletionMessageFunctionToolCall):
                        print("Harness> Potentially malformed tool call ...")
                        continue

                    print(f"Harness> Executing tool: {tool_call.function.name}")

                    result = execute_tool(
                        name=tool_call.function.name,
                        arguments=tool_call.function.arguments,
                    )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        }
                    )

                continue

            llm_reply = assistant_message.content

            if not llm_reply:
                raise RuntimeError("LLM response is empty.")

            print(f"LLM> {llm_reply}")

            messages.append(
                {
                    "role": "assistant",
                    "content": llm_reply,
                }
            )

            if (
                response.usage
                and response.usage.prompt_tokens >= CONTEXT_BUDGET * COMPACTION_THRESHOLD
            ):
                messages = compact_history(
                    messages=messages,
                    llm_client=llm_client,
                    model_name=model_name,
                    recent_turns_to_keep=RECENT_TURNS_TO_KEEP,
                )

            break

        else:
            print("Harness> Maximum model calls reached for this query.")


@query_source
def cli_input() -> str:
    return input("User> ")


def scripted_input(queries: list[str]) -> QuerySupplier:
    iterator = iter(queries)

    @query_source
    def get_next_query() -> str:
        return next(iterator, "exit")

    return get_next_query


if __name__ == "__main__":
    llm_client = OpenAI(
        base_url=require_env("MODEL_URL"),
        api_key=require_env("API_KEY"),
    )

    eval_input = scripted_input(
        [
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
    )

    agent_loop(llm_client, eval_input)
