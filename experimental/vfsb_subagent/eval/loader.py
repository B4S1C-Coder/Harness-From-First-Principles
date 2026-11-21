"""Read the Loghub Hadoop manifest and isolate one application's original log lines."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory

from harness.exceptions import ConfigurationError


class Label(StrEnum):
    NORMAL = "normal"
    MACHINE_DOWN = "machine_down"
    NETWORK_DISCONNECTION = "network_disconnection"
    DISK_FULL = "disk_full"


@dataclass(frozen=True)
class Job:
    id: str
    workload: str
    label: Label
    logs: tuple[Path, ...]


def load_jobs(root: Path) -> list[Job]:
    manifest = root / "abnormal_label.txt"
    if not manifest.is_file():
        raise ConfigurationError(f"Missing Hadoop label file: {manifest}")
    headings = {label.value.replace("_", " ").capitalize() + ":": label for label in Label}
    workload = ""
    label = None
    jobs: dict[str, Job] = {}
    for number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line in {"### WordCount", "### PageRank"}:
            workload, label = line[4:], None
        elif workload and line in headings:
            label = headings[line]
        elif match := re.fullmatch(r"\+\s+(application_(\d+_\d+))", line):
            job_id, suffix = match.groups()
            if label is None or job_id in jobs:
                raise ConfigurationError(f"{manifest}:{number}: missing or duplicate label: {line}")
            logs = tuple(sorted((root / job_id).glob(f"container_{suffix}_*.log")))
            if not logs:
                raise ConfigurationError(f"No container logs for labeled job {job_id}")
            jobs[job_id] = Job(job_id, workload, label, logs)
        elif workload or line.startswith(("+", "#")) or line.endswith(":"):
            raise ConfigurationError(f"{manifest}:{number}: unexpected label file entry: {line}")
        # Before the first workload the archive has a prose introduction.
    if not jobs:
        raise ConfigurationError(f"No labeled jobs in {manifest}")
    return list(jobs.values())


@contextmanager
def workspace(job: Job) -> Iterator[Path]:
    with TemporaryDirectory(prefix="hadoop-job-") as directory:
        root = Path(directory)
        for log in job.logs:
            (root / f"app-{log.name}").symlink_to(log.resolve(strict=True))
        yield root
