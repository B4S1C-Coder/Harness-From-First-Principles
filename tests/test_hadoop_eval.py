import json
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletionMessage

from experimental.vfsb_subagent.eval import meter, scorer
from experimental.vfsb_subagent.eval.loader import Job, Label, load_jobs, workspace
from experimental.vfsb_subagent.eval.records import Record, TurnResult, read_records
from experimental.vfsb_subagent.eval.runner import run_jobs, run_turn
from harness.log.log_backend import SQLiteLogs
from experimental.vfsb_frmwrk.run import build_agent
from harness.exceptions import ConfigurationError, UnexpectedResponseError
from harness.llms import SyncTextLLMClient
from harness.logger import ApplicationLogger
from harness.token_estimator import TokenEstimator


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    root = tmp_path / "dataset"
    root.mkdir()
    body = ["Introductory prose.", "", "### WordCount"]
    for i, title in enumerate(("Normal", "Machine down", "Network disconnection", "Disk full"), 1):
        if i == 3:
            body.append("### PageRank")
        suffix = f"1445087491445_{i:04d}"
        job_id = "application_" + suffix
        body.extend([f"{title}:", f"+ {job_id}", ""])
        folder = root / job_id
        folder.mkdir()
        for n in (1, 2):
            (folder / f"container_{suffix}_01_{n:06d}.log").write_bytes(
                f"2015-10-17 12:00:00,123 INFO [main] test: job {i}, file {n}\r\n"
                "  a continuation\r\n".encode()
            )
    (root / "abnormal_label.txt").write_bytes("\r\n".join(body).encode())
    return root


def test_loader_exposes_only_one_jobs_logs(dataset: Path) -> None:
    jobs = load_jobs(dataset)
    assert [j.label for j in jobs] == list(Label)
    assert [j.workload for j in jobs] == ["WordCount", "WordCount", "PageRank", "PageRank"]
    with workspace(jobs[1]) as root, closing(SQLiteLogs(root)) as db:
        assert sorted(p.name for p in root.iterdir()) == [f"app-{log.name}" for log in jobs[1].logs]
        assert db.query("SELECT count(*), count(timestamp) FROM logs").rows == [[4, 2]]
        assert [row[0] for row in db.query("SELECT message FROM logs WHERE line=1").rows] == [
            "job 2, file 1",
            "job 2, file 2",
        ]
    assert not root.exists() and jobs[1].logs[0].exists()


@pytest.mark.parametrize(
    "addition",
    [
        "Machine down:\n+ application_1445087491445_0001",
        "Unknown:",
        "### WordCount\n+ application_1_0001",
        "+ application_1_0002",
    ],
)
def test_invalid_manifest_fails_loudly(dataset: Path, addition: str) -> None:
    with (dataset / "abnormal_label.txt").open("a") as file:
        file.write("\n" + addition)
    with pytest.raises(ConfigurationError):
        load_jobs(dataset)


def sample_turn(root: Path) -> TurnResult:
    assert len(list(root.glob("app-*.log"))) == 2
    return TurnResult(
        report="Network disconnection.\nLost contact.",
        prompt_tokens=12,
        completion_tokens=3,
        requests=2,
        tool_turns=1,
        seconds=1.5,
    )


def test_resume_failed_job_partial_tail_and_limit(dataset: Path, tmp_path: Path) -> None:
    jobs = load_jobs(dataset)
    output = tmp_path / "resume.jsonl"
    calls = []

    def interrupted(root: Path) -> TurnResult:
        calls.append(root)
        if len(calls) == 2:
            raise UnexpectedResponseError("Test provider", "interrupted")
        return sample_turn(root)

    with pytest.raises(UnexpectedResponseError):
        run_jobs(jobs, output, interrupted)
    assert len(calls) == 2 and not any(root.exists() for root in calls)
    saved = output.read_bytes()
    assert len(saved.splitlines()) == 1
    with output.open("ab") as file:
        file.write(b'{"job_id": "unfinished')
    assert run_jobs(jobs, output, sample_turn, limit=1) == 1
    assert output.read_bytes().startswith(saved)
    assert run_jobs(jobs, output, sample_turn, limit=0) == 0
    assert run_jobs(jobs, output, sample_turn) == 2
    assert run_jobs(jobs, output, sample_turn) == 0
    with output.open("rb") as file:
        rows = list(read_records(file))
    assert [(r.job_id, r.label) for r in rows] == [(j.id, j.label) for j in jobs]
    assert all(r.report.endswith("\nLost contact.") for r in rows)


def test_resume_keeps_valid_final_line_and_rejects_corruption(
    dataset: Path, tmp_path: Path
) -> None:
    jobs = load_jobs(dataset)
    output = tmp_path / "results.jsonl"
    run_jobs(jobs, output, sample_turn, 1)
    saved = output.read_bytes()
    output.write_bytes(saved.rstrip(b"\n"))
    assert run_jobs(jobs, output, sample_turn, 1) == 1
    assert output.read_bytes().startswith(saved)
    for bad in (b"invalid\n", b'{"job_id": "only-id"}\n', saved):
        output.write_bytes(saved + bad)
        with pytest.raises(ConfigurationError):
            run_jobs(jobs, output, sample_turn)
        assert output.read_bytes() == saved + bad


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The job completed successfully.", Label.NORMAL),
        ("Machine down. Connection refused later.", Label.MACHINE_DOWN),
        ("NoRouteToHostException while writing", Label.NETWORK_DISCONNECTION),
        ("No evidence of machine failure. No space left on device.", Label.DISK_FULL),
        ("disk_full", Label.DISK_FULL),
        ("Inconclusive.", "unclassified"),
    ],
)
def test_keyword_rules(text: str, expected: str) -> None:
    assert scorer.classify(text) == expected


def test_score_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "scores.jsonl"
    rows = [
        Record(
            job_id=str(i),
            label=label,
            report=report,
            requests=i,
            tool_turns=i - 1,
            seconds=i / 2,
            prompt_tokens=i * 10,
            completion_tokens=i,
        )
        for i, (label, report) in enumerate(
            zip(
                Label,
                [
                    "Inconclusive.",
                    "Network disconnection",
                    "Normal run",
                    "Disk full",
                ],
                strict=True,
            ),
            1,
        )
    ]
    output.write_text("".join(json.dumps(asdict(r)) + "\n" for r in rows))
    monkeypatch.setattr("sys.argv", ["scorer", str(output)])
    scorer.main()
    scores = json.loads(capsys.readouterr().out)
    assert scores["jobs"] == 4
    assert scores["exact_accuracy"] == 0.25 and scores["coarse_accuracy"] == 0.5
    assert scores["mean_tokens"] == 27.5 and scores["mean_requests"] == 2.5
    assert scores["mean_seconds"] == 1.25
    matrix = scores["confusion_matrix"]
    assert matrix["machine_down"]["network_disconnection"] == 0
    assert matrix["unclassified"]["normal"] == 1
    assert matrix["network_disconnection"]["machine_down"] == 1
    assert all(set(row) == set(Label) for row in matrix.values())
    assert scorer.score([]).exact_accuracy is None


def test_measured_turn_counts_helper_and_paces_across_jobs(
    dataset: Path, app_logger: ApplicationLogger, monkeypatch: pytest.MonkeyPatch
) -> None:
    import experimental.vfsb_frmwrk.run as agent_module

    monkeypatch.setattr(agent_module, "TokenEstimator", lambda: TokenEstimator(encoding=None))
    replies = iter(
        [
            ChatCompletionMessage(
                role="assistant",
                tool_calls=[
                    {
                        "type": "function",
                        "id": "q",
                        "function": {
                            "name": "advanced_log_analysis",
                            "arguments": '{"request":"Count log lines"}',
                        },
                    }
                ],
            ),
            ChatCompletionMessage(role="assistant", content="SELECT count(*) FROM logs"),
            ChatCompletionMessage(role="assistant", content="Normal run"),
            ChatCompletionMessage(role="assistant", content="Disk full"),
        ]
    )
    models = []

    def generate(
        client: SyncTextLLMClient, tools: list, messages: list, *, dangerously_ignore_usage: bool
    ) -> tuple:
        assert not dangerously_ignore_usage
        models.append(client.model)
        return (
            SimpleNamespace(
                choices=[SimpleNamespace(message=next(replies))],
                usage=SimpleNamespace(completion_tokens=3),
            ),
            10,
            4,
        )

    for key, value in {"MODEL_URL": "http://unused.invalid", "API_KEY": "fake"}.items():
        monkeypatch.setenv(key, value)
    waits = []
    monkeypatch.setattr(meter, "time", SimpleNamespace(monotonic=lambda: 100, sleep=waits.append))
    monkeypatch.setattr(SyncTextLLMClient, "generate_next", generate)
    usage = meter.Meter()
    main, helper = (meter.MeteredClient(model, usage) for model in ("main", "helper"))
    jobs: list[Job] = load_jobs(dataset)
    results = []
    for job in jobs[:2]:
        with workspace(job) as root, closing(SQLiteLogs(root)) as db:
            agent = build_agent(db, app_logger, main, helper, "Investigate")
            results.append(run_turn(agent, usage))
    a, b = results
    assert models == ["main", "helper", "main", "main"] and waits == [60] * 3
    assert a.report == "Normal run" and a.tool_turns == 1 and a.requests == 3
    assert (a.prompt_tokens, a.completion_tokens, a.total_tokens) == (30, 9, 39)
    assert (b.report, b.tool_turns, b.requests, b.total_tokens) == ("Disk full", 0, 1, 13)
    assert a.seconds >= 0 and b.seconds >= 0


@pytest.mark.parametrize(
    ("has_tools", "code", "request_count"),
    [
        (False, "tool_use_failed", 2),
        (True, "tool_use_failed", 1),
        (False, "invalid_request_error", 1),
    ],
)
def test_text_only_retry_stays_bounded(
    monkeypatch: pytest.MonkeyPatch,
    has_tools: bool,
    code: str,
    request_count: int,
) -> None:
    from unittest.mock import Mock

    from openai import BadRequestError

    api_error = BadRequestError("Rejected", response=Mock(), body={"code": code})
    calls = []

    def reject(client: SyncTextLLMClient, tools: list, messages: list, **kwargs: bool) -> tuple:
        calls.append((tools, messages))
        raise UnexpectedResponseError("Provider", "Rejected") from api_error

    monkeypatch.setenv("MODEL_URL", "http://unused.invalid")
    monkeypatch.setenv("API_KEY", "fake")
    monkeypatch.setattr(SyncTextLLMClient, "generate_next", reject)
    monkeypatch.setattr(meter, "time", SimpleNamespace(monotonic=lambda: 100, sleep=lambda _: None))
    usage = meter.Meter()
    client = meter.MeteredClient("main", usage)
    original = [{"role": "tool", "tool_call_id": "q", "content": "observed source line"}]
    with pytest.raises(UnexpectedResponseError):
        client.generate_next([{}] if has_tools else [], original)
    assert len(calls) == usage.requests == request_count
    assert usage.prompt_tokens == usage.completion_tokens == 0
    if request_count == 2:
        tools, messages = calls[1]
        assert tools == [] and messages[-1]["role"] == "user"
        assert original[0]["role"] == "tool" and messages[0]["role"] == "user"
        assert original[0]["content"] in messages[0]["content"]
