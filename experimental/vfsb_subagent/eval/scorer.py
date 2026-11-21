"""Score completed Hadoop investigations against the labels shipped with Loghub."""

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean

from .loader import Label
from .records import Record, read_records

# Handoffs lead with the finding. Use the first affirmative match in reading order.
KEYWORDS = {
    Label.NORMAL: r"ran normally|normal (?:run|completion)|completed successfully|"
    r"no (?:evidence of (?:a |an )?)?(?:failure|fault|anomal)|\bnormal\b",
    Label.DISK_FULL: r"disk (?:is |was )?full|no space left|out of (?:disk )?space|"
    r"disk space exhaust|\benospc\b",
    Label.MACHINE_DOWN: r"(?:machine|node|host|server) (?:is |was |went )?"
    r"(?:down|offline)|(?:machine|node|host|server) (?:crash|failure)|lost (?:a )?node",
    Label.NETWORK_DISCONNECTION: r"network (?:disconn|connectivity|partition|outage|failure)|"
    r"no ?route ?to ?host|connection (?:reset|refused|timed out)|unreachable",
}
NEGATED = re.compile(r"\b(?:no evidence of|without|ruled out|not|no) (?:an? )?$")
COARSE = {
    Label.NORMAL: "none",
    Label.DISK_FULL: "disk",
    Label.MACHINE_DOWN: "connectivity",
    Label.NETWORK_DISCONNECTION: "connectivity",
}


def classify(report: str) -> Label:
    text = report.casefold().replace("_", " ").replace("-", " ").replace("*", "")
    first: tuple[int, Label] | None = None
    for label, pattern in KEYWORDS.items():
        for match in re.finditer(pattern, text):
            if NEGATED.search(text[max(0, match.start() - 24) : match.start()]):
                continue
            if first is None or match.start() < first[0]:
                first = match.start(), label
            break
    return first[1] if first else Label.NORMAL


@dataclass(frozen=True)
class Scores:
    jobs: int
    confusion_matrix: dict[Label, dict[Label, int]]
    exact_accuracy: float | None
    coarse_accuracy: float | None
    mean_tokens: float | None
    mean_requests: float | None
    mean_seconds: float | None


def score(records: Iterable[Record]) -> Scores:
    rows = list(records)
    matrix = {truth: dict.fromkeys(Label, 0) for truth in Label}
    exact = coarse = 0
    for row in rows:
        predicted = classify(row.report)
        matrix[row.label][predicted] += 1
        exact += predicted == row.label
        coarse += COARSE[predicted] == COARSE[row.label]
    n = len(rows)
    return Scores(
        n,
        matrix,
        exact / n if n else None,
        coarse / n if n else None,
        fmean(row.total_tokens for row in rows) if n else None,
        fmean(row.requests for row in rows) if n else None,
        fmean(row.seconds for row in rows) if n else None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, help="Runner JSONL file")
    args = parser.parse_args()
    with args.results.open("rb") as file:
        scores = score(read_records(file))
    sys.stdout.write(json.dumps(asdict(scores), indent=2) + "\n")


if __name__ == "__main__":
    main()
