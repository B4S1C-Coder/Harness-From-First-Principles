"""Completed-job JSONL schema shared by resume and scoring."""

import json
import math
from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO

from harness.exceptions import ConfigurationError
from .loader import Label


@dataclass(frozen=True, kw_only=True)
class TurnResult:
    report: str
    prompt_tokens: int
    completion_tokens: int
    requests: int
    tool_turns: int
    seconds: float

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, kw_only=True)
class Record(TurnResult):
    job_id: str
    label: Label


def read_records(file: BinaryIO, *, repair_tail: bool = False) -> Iterator[Record]:
    """Under a writer lock, recover an interrupted append at EOF only."""
    seen = set()
    for number, line in enumerate(file, 1):
        try:
            data = json.loads(line)
        except (ValueError, UnicodeDecodeError) as exc:
            if repair_tail and not line.endswith(b"\n"):
                file.truncate(file.tell() - len(line))
                return
            raise ConfigurationError(f"Invalid JSON on results line {number}") from exc
        try:
            data["label"] = Label(data["label"])
            record = Record(**data)
            valid = (
                isinstance(record.job_id, str)
                and record.job_id
                and record.job_id not in seen
                and isinstance(record.report, str)
                and record.report.strip()
                and all(
                    type(n) is int and n >= 0
                    for n in (
                        record.prompt_tokens,
                        record.completion_tokens,
                        record.tool_turns,
                        record.requests,
                    )
                )
                and record.requests > record.tool_turns
                and math.isfinite(record.seconds)
                and record.seconds >= 0
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise ConfigurationError(f"Invalid job record on results line {number}") from exc
        if not valid:
            raise ConfigurationError(f"Incomplete or duplicate job on results line {number}")
        if repair_tail and not line.endswith(b"\n"):
            file.write(b"\n")
        seen.add(record.job_id)
        yield record
