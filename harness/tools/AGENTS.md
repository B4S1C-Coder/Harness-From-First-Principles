# harness/tools

## Purpose
- Define tool schemas, register tool classes, and validate and execute explicitly bound tool instances.

## Public interface
- Package exports: `BaseTool`, `ToolRegistry`, `ToolExecutor`, `ToolExecutionLimits`.
- `BaseTool`: subclasses supply `name: str`, `description: str`, `parameters: dict[str, Any]`.
- `BaseTool.driver(self, args: dict[str, Any]) -> dict[str, Any]` is abstract.
- `BaseTool.definition() -> dict[str, Any]` is a classmethod returning an OpenAI function definition with `strict=True`.
- `ToolRegistry.register[T: BaseTool](tool_cls: type[T]) -> type[T]` is a classmethod/decorator.
- `ToolRegistry.class_definitions() -> dict[str, dict[str, Any]]` is a classmethod.
- `ToolExecutionLimits(max_argument_bytes: int = 64 * 1024, max_result_bytes: int = 128 * 1024)` is a frozen dataclass.
- `ToolExecutor(logger: ApplicationLogger, tools: Iterable[BaseTool], *, limits: ToolExecutionLimits | None = None) -> None`.
- `ToolExecutor.definitions(self) -> dict[str, dict[str, Any]]`; `execute(self, name: str, args: dict[str, Any]) -> str`.

## Contracts
- Registry registration stores classes globally by name, returns the class, and raises `ValueError` for duplicate names.
- Limits must be positive; otherwise construction raises `ValueError`.
- Known deviation: the `ValueError`s above should become `harness/exceptions.py` types. Don't copy this pattern in new code.
- Executor callers supply instances whose names are registered; construction raises `UnregisteredToolError` or `DuplicateToolError` for invalid bindings.
- Invalid tool schemas raise at construction.
- Execution requires dictionary arguments serializable with `allow_nan=False`, within the UTF-8 byte limit, and valid against the instance schema.
- Unavailable tools and rejected arguments return JSON errors without calling the driver.
- Execution returns JSON containing `success` and either `data` or `error`; oversized encoded responses return a size-error JSON object.
- Driver/result-encoding exceptions are logged and converted to errors.
- Drivers receive the original argument dictionary; their side effects are not rolled back.

## Dependencies
- Imports `ApplicationLogger` from `harness.logger` and `harness.exceptions`; uses `jsonschema` validation.
- Other imports are standard library modules and sibling tool modules.
- Forbidden imports: `agents/`, `llms/`, `sandboxes/`, `builtin_tools/`, `compaction.py`.

## Testing
- `uv run pytest tests/test_tool_executor.py tests/test_registry_register_tools.py -v`

## Gotchas
- Registry membership is checked by name, not class identity; definitions come from registered classes, validators from supplied instances.
- `definitions()` returns the executor's internal mapping directly; definition parameter dictionaries are not copied.
- Registration does not instantiate tools.

## Known issues
- Registry/limits `ValueError`s should use `harness/exceptions.py` (low priority).
- Oversized-response fallback isn't checked against `max_result_bytes`.