import pytest
from pathlib import Path
from collections.abc import Generator
from typing import Any

from harness.prompts import PromptStore
from harness.logger import ApplicationLogger

### IMPORTANT ###
# -----------------------------------------------------------------------------------
# Generator[Yield Type, Send Type, Return Type]
# * Yield Type: The type that is returned to caller when it encounters `yield` keyword
# * Send Type: The type of data that can be passed into the generator via `gen.send(val)`
# * Return Type: The type of the value returned when generator finishes execution entirely
# *              via the `return statement`.
# -----------------------------------------------------------------------------------
# When the generator yields an instance of the class use:
# * Generator[T, Any, None]
# When the generator yield the class itself NOT AN INSTANCE use:
# * Generator[type[T], Any, None]

@pytest.fixture
def prompt_store(tmp_path: Path) -> Generator[type[PromptStore], Any, None]:
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

@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    """ Provide an isolated directory for log files. """
    return tmp_path / "logs"

@pytest.fixture
def app_logger(log_dir: Path) -> Generator[ApplicationLogger, Any, None]:
    """ Provide a configured ApplicationLogger instance. """

    logger = ApplicationLogger(
        log_dir=log_dir, max_bytes=1024 * 1024, backup_count=2
    )

    yield logger
    logger.close()