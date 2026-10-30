import pytest
from pathlib import Path

from harness.prompts import PromptStore

@pytest.fixture
def prompt_store(tmp_path: Path):
    """ Initialize PromptStore with a temporary database. """

    project_root = Path(__file__).parent.parent
    sql_directory = project_root / "harness" / "sql"

    # Explicitly close any existing connection, to make tests execution order independent
    PromptStore.close()

    PromptStore.initialize(
        database=tmp_path / "test.db",
        sql_directory=sql_directory,
    )

    yield PromptStore

    PromptStore.close()