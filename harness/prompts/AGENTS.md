# harness/prompts

## Purpose
- Store versioned prompt templates in SQLite and load them with placeholders filled.

## Public interface
- `from harness.prompts import PromptStore`; all methods are class methods.
- `PromptStore.initialize(database: Path, sql_directory: Path = PKG_ROOT_DIR / "sql")`
- `PromptStore.load_prompt(_prompt_name: str, *, version: int | None = None, **kwargs: Any) -> str`
- `PromptStore.add_prompt(_prompt_name: str, template: str, *, description: str | None = None, change_note: str | None = None) -> int`
- `PromptStore.close() -> None`

## Contracts
- Initialize before adding or loading; one connection is shared by the class.
- Initialization creates database parent directories, opens SQLite, enables foreign keys, and runs schema SQL.
- SQL directory must supply `schema/schema_prompt.sql`, `schema/schema_prompt_version.sql`, and the queries used below.
- Required queries: `prompts/{get_prompt,insert_prompt,get_latest_version,get_version,insert_version}.sql`.
- `add_prompt` returns the prompt family ID; new families start at version 1.
- Changed templates append a version; a template equal to the latest creates no version.
- Description is supplied only when creating a family; change notes accompany new versions.
- Adds commit on success and roll back on failure.
- Loading defaults to the latest version; an explicit version selects that version.
- Templates use Python string-format placeholders filled from `kwargs`.
- `RuntimeError`: already initialized, no SQL files, or add/load before initialization.
- `LookupError`: requested prompt or version is absent.
- Filesystem, SQLite, missing-query `KeyError`, and template-formatting errors propagate.
- `close` releases the connection and allows reinitialization; closing again is harmless.

## Dependencies
- Imports `PKG_ROOT_DIR` from `harness` for the default SQL directory.

## Testing
- `uv run pytest tests/test_prompt_store.py -v`

## Gotchas
- Methods raise built-in errors directly; they do not use `harness.exceptions`. This is a known issue which needs to be fixed later.
- Reusing an unchanged template does not update its description or change note.
