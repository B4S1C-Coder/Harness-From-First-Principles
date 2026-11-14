# harness/builtin_tools

## Purpose
- Ready-to-use synchronous tools: dummy responses and sandboxed filesystem operations.

## Public interface
- Import tools from `dummy_tools` or `virtual_fs`; `__init__.py` exports nothing.
- Dummy constructors: `list_directory()` and `WeatherTool()`.
- Filesystem constructors: `ListDirectoryTool`, `ReadFileTool`, `ReadLinesTool`, `WriteFileTool`, `EditFileTool`, each `(sandbox: VirtualFileSystemSandbox, *, limit: VirtualFSReadLimits | None = None)`.
- `VirtualFSTool` supplies the shared constructor; it is an abstract base.
- All concrete tools expose `driver(self, args: dict[str, Any]) -> dict[str, Any]` and inherited `definition()`; schemas are in `parameters`.
- Dummy arguments/results: `{path}` → `{path, entries}`; `{location}` → `{location, temperature_celsius, condition}`.
- Filesystem arguments/results: list `{path}` → `{path, listing}`; read `{path}` → `{path, content}`.
- Read lines `{path, start_line, end_line}` → `{path, start_line, end_line, truncated_range, content}`.
- Write `{path, content, overwrite}` → `{path, written}`; edit `{path, start_line, end_line, content}` → `{path, edited, start_line, end_line}`.

## Contracts
- Drivers assume schema-conforming arguments; required keys are accessed directly and missing keys can raise `KeyError`.
- Dummy tools return fixed entries or weather values; they perform no directory or weather lookup.
- Filesystem tools require a sandbox; paths are workspace-relative and sandbox permissions apply.
- Reads default to 8192 bytes and 100 lines; file reads use the byte limit, line reads use both limits.
- Line ranges are inclusive and start at 1; read-line end is capped by `max_lines` and returned as `end_line`.
- `ReadLinesTool` raises `ValueValidationError` when requested end precedes start.
- Sandbox errors propagate, including `PermissionDenied`, `NotADirectory`, `ToolExecutionError`, `ValueValidationError`, and filesystem/encoding errors.
- Write creates or replaces UTF-8 text; parents must exist. Edit replaces existing lines; empty content deletes the range.
- Importing either tool module registers its concrete classes in the global `ToolRegistry`.

## Dependencies
- `harness.tools`: `BaseTool`, `ToolRegistry`.
- `harness.sandboxes`: `VirtualFileSystemSandbox`; `harness.limits`: `VirtualFSReadLimits`.
- `harness.exceptions`: `ValueValidationError`.

## Testing
- `uv run pytest tests/test_registry_register_tools.py tests/test_tool_executor.py -v` covers dummy tools via registry/executor tests; no filesystem-tool tests exist.

## Gotchas
- Dummy and filesystem directory tools share `list_directory`; importing both modules raises registry `ValueError` for the duplicate name.
- Write schema requires `overwrite` despite its default of false; direct driver calls default omitted `overwrite` to false.
- `truncated_range` reports only the line-range cap; byte truncation is indicated in returned content. Returned end does not indicate actual EOF.
