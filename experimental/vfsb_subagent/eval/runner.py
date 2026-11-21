"""Run one isolated investigation at a time and checkpoint each completed report."""

import argparse
import fcntl
import json
import os
import time
from collections.abc import Callable, Iterable
from contextlib import closing
from dataclasses import asdict, replace
from itertools import islice
from pathlib import Path

from dotenv import load_dotenv

from harness.exceptions import ConfigurationError
from harness.logger import ApplicationLogger
from harness.prompts import PromptStore
from harness.shortcuts.generic_scmt import SCMTTAgent
from ..log_backend import SQLiteLogs
from ..run import PROMPT_ROOT, ROOT, build_agent, investigate_turn
from .loader import Job, load_jobs, workspace
from .meter import Meter, MeteredClient
from .records import Record, TurnResult, read_records

DATA = ROOT / "data"
QUESTION = (
    "Investigate this Hadoop job. Did it run normally or is there evidence of a failure? "
    "Identify the most likely underlying issue, distinguish secondary symptoms, and cite "
    "specific timestamps and log lines. State any uncertainty."
)


def run_turn(agent: SCMTTAgent, meter: Meter, query: str = QUESTION) -> TurnResult:
    before = replace(meter)
    start = time.monotonic()
    report, tool_turns = investigate_turn(agent, query)
    return TurnResult(
        report=report,
        prompt_tokens=meter.prompt_tokens - before.prompt_tokens,
        completion_tokens=meter.completion_tokens - before.completion_tokens,
        requests=meter.requests - before.requests,
        tool_turns=tool_turns,
        seconds=time.monotonic() - start,
    )


def run_jobs(
    jobs: Iterable[Job],
    output: Path,
    investigate: Callable[[Path], TurnResult],
    limit: int | None = None,
) -> int:
    if limit is not None and limit < 0:
        raise ConfigurationError("--limit must be nonnegative")
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("a+b") as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        file.seek(0)
        finished = {row.job_id for row in read_records(file, repair_tail=True)}
        for job in islice((j for j in jobs if j.id not in finished), limit):
            with workspace(job) as root:
                result = investigate(root)
            row = Record(job_id=job.id, label=job.label, **asdict(result))
            file.write((json.dumps(asdict(row)) + "\n").encode())
            file.flush()
            os.fsync(file.fileno())
            finished.add(job.id)
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATA / "loghub_hadoop")
    parser.add_argument("--output", type=Path, default=DATA / "hadoop-results.jsonl")
    parser.add_argument("--limit", type=int, help="Maximum new jobs in this invocation")
    args = parser.parse_args()
    jobs = load_jobs(args.dataset)
    load_dotenv()
    meter = Meter()
    main_client = MeteredClient("openai/gpt-oss-120b", meter)
    helper = MeteredClient("openai/gpt-oss-20b", meter)
    PromptStore.initialize(PROMPT_ROOT / "prompts.db")
    try:
        prompt = PromptStore.load_prompt("experimental.vfsb_subagent.main.system")
    finally:
        PromptStore.close()
    with closing(ApplicationLogger(DATA)) as logger:

        def investigate(root: Path) -> TurnResult:
            with closing(SQLiteLogs(root)) as db:
                return run_turn(build_agent(db, logger, main_client, helper, prompt), meter)

        run_jobs(jobs, args.output, investigate, args.limit)


if __name__ == "__main__":
    main()
