# harness/agents

## Purpose

- Provide a synchronous, generic agent base with conversation history and subclass response handlers.

## Public interface

- Export generic `SynchronousAgentBase[ConfigT]` from `harness.agents`; `__init__` is marked `@final`.
- Constructor: `SynchronousAgentBase(client: SyncTextLLMClient, logger: ApplicationLogger, system_prompt: str, *, config: ConfigT | None = None, tools: list[ChatCompletionToolParam] | None = None, context_budget: int = 8_000, compaction_threshold: float = 0.8, recent_turns_to_keep: int = 2, enable_context_check: bool = True, compaction: Callable[[list[ChatCompletionMessageParam], SyncTextLLMClient, int], list[ChatCompletionMessageParam]] = naive_compaction) -> None`.
- Abstract handlers: `handle_message(self, message: ChatCompletionMessage) -> bool`, `handle_tool_call(self, message: ChatCompletionMessage) -> bool`.
- Methods: `add_user_message(self, content: str) -> None`, `step(self) -> bool`, `reset(self) -> None`.
- Context manager: `turn(self) -> Generator[None]` establishes a logger correlation scope.
- `post_init(self, config: ConfigT | None) -> None`: application-specific setup hook, called at the end of the base `__init__`. Never override `__init__`; put setup here.

## Contracts

- Initialization stores dependencies and settings, seeds the system message, then calls `post_init(config)`.
- Subclasses implement all three abstract hooks; handler results mean continue (`True`) or end (`False`) the turn.
- `step()` calls `client.generate_next(self.tools, self.messages)` and uses the first response choice.
- The client must return `(response, input_tokens, cached_tokens)`; token counts are logged.
- No choices raises `UnexpectedResponseError` with the agent class name.
- Append the serialized assistant message before dispatching to the tool-call or normal handler.
- With `enable_context_check=False`, skip the estimate, automatic compaction, and size rejection entirely. This bypass does not change provider limits.
- By default, before each model request, estimate serialized messages and tools conservatively at one UTF-8 byte per token. At budget times threshold, invoke the configured compaction callable and recheck; failure or an oversized result raises `UnexpectedResponseError` before any investigation request. Final reports remain untouched after handlers return.
- `add_user_message` ignores empty content; `reset` replaces history with the current system prompt.
- Client, logger, handler, and serialization exceptions propagate; compaction failures are wrapped in `UnexpectedResponseError`.
- `step()` advances the agent by exactly one LLM turn. Callers own the conversation loop. Don't add looping or auto-run behavior to the base class.

## Dependencies

- Import `naive_compaction` from `harness.compaction`, `UnexpectedResponseError` from `harness.exceptions`.
- Import `SyncTextLLMClient` from `harness.llms`, `ApplicationLogger` from `harness.logger`.
- Use OpenAI Chat Completions message and tool types
- Within `harness`, depend only on `llms`, `logger`, `compaction`, `exceptions`. Ask before importing any other harness package.

## Testing
- No automated tests for this package. Don't add tests that call a real LLM.
- If tests are added later, use a fake `SyncTextLLMClient`.

## Gotchas

- `post_init` is abstract on purpose: any agent with tools must build its `ToolExecutor` there. Subclasses with no setup still implement it (a bare `pass` is fine). Don't make it optional or rely on the base body.
- Supplied tools are retained by reference; compaction and reset replace the messages list.
