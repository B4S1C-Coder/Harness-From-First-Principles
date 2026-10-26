import sqlite3
from pathlib import Path
from typing import Any

class PromptStore:
    _connection: sqlite3.Connection | None = None
    _queries: dict[str, str] = {}

    @classmethod
    def initialize(cls, database: Path, sql_directory: Path):
        """ Initializes Sqlite connection and tables. """

        if cls._connection is not None:
            raise RuntimeError("PromptStore is already initialized.")
        
        cls._queries = {
            str(path.relative_to(sql_directory)): path.read_text(
                encoding="utf-8"
            )
            for path in sql_directory.rglob("*.sql")
        }

        database.parent.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        try:
            for schema_file in (
                "schema/schema_prompt.sql",
                "schema/schema_prompt_version.sql"
            ):
                connection.executescript(cls._queries[schema_file])
        except Exception:
            connection.close()
            cls._queries.clear()
            raise

        cls._connection = connection
    
    @classmethod
    def load_prompt(cls, name: str, *, version: int | None = None, **kwargs: Any) -> str:
        """ Loads the specified prompt with filled in placeholders. """

        if cls._connection is None:
            raise RuntimeError("Call PromptStore.initialize() first")
        
        if version is None:
            query = cls._queries["prompts/get_latest_version.sql"]
            row = cls._connection.execute(query, (name,)).fetchone()
        else:
            query = cls._queries["prompts/get_version.sql"]
            row = cls._connection.execute(query, (name, version,)).fetchone()

        if row is None:
            raise LookupError(
                f"Prompt {name!r}"
                + (f", version {version}" if version is not None else "")
                + " was not found"
            )
        
        return row["template"].format(**kwargs)
    
    @classmethod
    def add_prompt(
        cls,
        name: str,
        template: str,
        *, # All args after it are keyword only
        description: str | None = None,
        change_note: str | None = None,
    ) -> int:
        """
        Create a prompt family or add a version if template is changed. Returns prompt family id.
        """
        if cls._connection is None:
            raise RuntimeError("Call PromptStore.initialize() first")
        
        connection = cls._connection

        with connection:
            row = connection.execute(
                cls._queries["prompts/get_prompt.sql"],
                (name,),
            ).fetchone()

            if row is None:
                cursor = connection.execute(
                    cls._queries["prompts/insert_prompt.sql"],
                    (name, description),
                )
                prompt_id = cursor.fetchone()["id"]
                next_version = 1
            
            else:
                prompt_id = row["id"]

                latest = connection.execute(
                    cls._queries["prompts/get_latest_version.sql"],
                    (name,),
                ).fetchone()

                if latest["template"] == template:
                    return prompt_id
                
                next_version = latest["version"] + 1
            
            connection.execute(
                cls._queries["prompts/insert_version.sql"],
                (prompt_id, next_version, template, change_note),
            )
        
        return prompt_id
    
    @classmethod
    def close(cls) -> None:
        if cls._connection is not None:
            cls._connection.close()
            cls._connection = None