from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass, fields
from pathlib import Path

from harness.exceptions import ConfigurationError
from harness.prompts import PromptStore

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT.parent / "examples/data/prompts.db"


@dataclass(frozen=True)
class Prompts:
    master: str
    logs: str
    research: str


@contextmanager
def prompt_store(database: Path = DATABASE) -> Iterator[None]:
    PromptStore.initialize(database)
    try:
        yield
    finally:
        PromptStore.close()


def register() -> None:
    for field in fields(Prompts):
        key = f"rca.{field.name}.system"
        try:
            PromptStore.load_prompt(key)
        except KeyError:
            # An existing customized template may require format parameters.
            continue
        except LookupError:
            draft = ROOT / "prompts" / f"{field.name}.md"
            PromptStore.add_prompt(key, draft.read_text(encoding="utf-8").strip())


def load_prompts() -> Prompts:
    values = {}
    for field in fields(Prompts):
        key = f"rca.{field.name}.system"
        try:
            values[field.name] = PromptStore.load_prompt(key)
        except KeyError as exc:
            raise ConfigurationError(f"{key} contains an unsupported placeholder: {exc}") from exc
        except LookupError as exc:
            raise ConfigurationError(f"Missing {key}. Run 'uv run python -m rca.prompts'.") from exc
    return Prompts(**values)


if __name__ == "__main__":
    with prompt_store():
        register()
