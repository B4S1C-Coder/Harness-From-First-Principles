# harness/shortcuts

## Purpose
- Convenience factories for filesystem tool executors and a synchronous single-conversation, multiple-tool-turn agent.

## Public interface
- `fs_toolkit.virtual_fs_toolkit(root: Path, logger: ApplicationLogger, limits: ToolExecutionLimits | None = None) -> ToolExecutor`
- `fs_toolkit.virtual_readonly_fs_toolkit(root: Path, logger: ApplicationLogger, limits: ToolExecutionLimits | None = None) -> ToolExecutor`
- `generic_scmt.SCMTTConfig(tools: Iterable[BaseTool])` is a dataclass.
- `generic_scmt.SCMTTAgent[ConfigT: SCMTTConfig]` extends `SynchronousAgentBase[ConfigT]`.
- Inherited constructor (also accepts all current base options including `max_tool_turns`, `enable_context_check`, and `compaction`): `SCMTTAgent(client: SyncTextLLMClient, logger: ApplicationLogger, system_prompt: str, *, config: ConfigT | None = None, tools: list[ChatCompletionToolParam] | None = None, context_budget: int = 8_000, compaction_threshold: float = 0.8, recent_turns_to_keep: int = 2) -> None`.
- Hooks: `post_init(config: ConfigT | None) -> None`, `handle_message(message: ChatCompletionMessage) -> bool`, `handle_tool_call(message: ChatCompletionMessage) -> bool`.
- Inherited conversation methods: `add_user_message(content: str) -> None`, `step() -> bool`, `reset() -> None`, `turn() -> Generator[None]` (context manager).

## Contracts
- Both factories require an existing directory root; neither enables execution.
- Writable toolkit provides directory listing, file reading, line reading, editing and writing; readonly toolkit provides the first three only.
- Default limits are 64 KiB arguments and 128 KiB results; supplied limits are passed to the executor.
- Invalid roots propagate filesystem errors; a root that is not a directory raises `NotADirectory`.
- Agent config supplies registered, uniquely named tools; executor construction can raise `UnregisteredToolError` or `DuplicateToolError`.
- Normal nonempty responses print `LLM Reply> {content}` to stdout and return `False`; empty content raises `UnexpectedResponseError`.
- Tool calls execute sequentially, append tool responses to conversation history, log activity and return `True`.
- DEBUG application logs record tool call IDs, names and raw arguments, then result success/error and byte size. Tabular results additionally log row count, truncation and filename/line references when available; generated queries are logged without full evidence rows.
- Malformed JSON arguments and unsupported tool-call types append JSON failure responses; unsupported calls also log a warning.
- Executor-handled tool failures become JSON responses; exceptions outside that handling propagate.
- Executing writable filesystem tools can change files under the sandbox root.

## Dependencies
- Direct harness imports: `harness.agents`, `harness.tools`, `harness.exceptions`, `harness.sandboxes`, `harness.builtin_tools.virtual_fs`, `harness.logger`.

## Testing
- no tests

## Gotchas
- `__init__.py` is empty; import public names from their modules.
- Agent initialization replaces constructor-supplied tool definitions with definitions from config tools; absent config means no tools.
- The inherited optional `max_tool_turns` enforces a tools-disabled summary after the configured number of tool turns.
- Importing `fs_toolkit` imports the filesystem tools, registering their classes globally.
