import json
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletionMessage

from experimental.vfsb_subagent import log_evidence, log_preamble
from experimental.vfsb_subagent.log_backend import SQLiteLogs
from experimental.vfsb_subagent.run import (
    build_agent,
    run_turn,
    MAIN_AGENT_MAX_STEPS,
    MAIN_AGENT_MAX_TOOL_TURNS,
)
from harness.exceptions import ToolExecutionError, UnexpectedResponseError
from harness.logger import ApplicationLogger
from harness.token_estimator import TokenEstimator


class FakeClient:
    def __init__(self, replies: list[ChatCompletionMessage]) -> None:
        self.replies = iter(replies)
        self.calls = []

    def generate_next(self, tools: list, messages: list) -> tuple:
        self.calls.append((list(tools), list(messages)))
        return SimpleNamespace(choices=[SimpleNamespace(message=next(self.replies))]), 1, 0


def test_main_agent_owns_evidence_and_helper_only_receives_query_request(
    tmp_path: Path,
    app_logger: ApplicationLogger,
) -> None:
    (tmp_path / "app-01.log").write_text("2025-01-01 00:00:00,000 ERROR [t] app: failure\n")
    backend = SQLiteLogs(tmp_path)
    main_client = FakeClient(
        [
            ChatCompletionMessage(
                role="assistant",
                tool_calls=[
                    {
                        "id": "overview",
                        "type": "function",
                        "function": {
                            "name": "incident_digest",
                            "arguments": json.dumps(
                                dict.fromkeys(["start", "end", "level", "filename"])
                            ),
                        },
                    }
                ],
            ),
            *[
                ChatCompletionMessage(
                    role="assistant",
                    tool_calls=[
                        {
                            "id": name,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)},
                        }
                    ],
                )
                for name, args in (
                    ("scan_signatures", {"custom": []}),
                    ("timeline", {"start": "2025", "end": "2026", "filename": None}),
                    ("nearby_logs", {"refs": [{"filename": "app-01.log", "line": 1}], "radius": 1}),
                )
            ],
            ChatCompletionMessage(
                role="assistant",
                tool_calls=[
                    {
                        "id": "aggregate",
                        "type": "function",
                        "function": {
                            "name": "advanced_log_analysis",
                            "arguments": json.dumps({"request": "Count ERROR events"}),
                        },
                    }
                ],
            ),
            ChatCompletionMessage(role="assistant", content="One error; cause remains uncertain."),
        ]
    )
    query_client = FakeClient(
        [
            ChatCompletionMessage(
                role="assistant", content="SELECT count(*) FROM logs WHERE level = 'ERROR'"
            )
        ]
    )
    try:
        agent = build_agent(backend, app_logger, main_client, query_client, "Own the investigation")
        for tool in agent.tools:
            schema = tool["function"]["parameters"]
            assert set(schema["properties"]) == set(schema.get("required", [])), tool["function"][
                "name"
            ]
        assert {tool["function"]["name"] for tool in agent.tools} == {
            "incident_digest",
            "timeline",
            "scan_signatures",
            "search_logs",
            "nearby_logs",
            "advanced_log_analysis",
        }
        assert agent.max_tool_turns == MAIN_AGENT_MAX_TOOL_TURNS
        assert MAIN_AGENT_MAX_STEPS == MAIN_AGENT_MAX_TOOL_TURNS + 1
        assert agent.enable_context_check and agent.token_estimator is not None
        agent.add_user_message("Investigate the Hadoop failure using your log-analysis specialist.")
        assert agent.step() is True
        _, first = main_client.calls[0]
        assert [m["role"] for m in first] == ["system", "user", "user"]
        pack = json.loads(first[1]["content"].removeprefix(log_preamble.PACK_PREFIX))
        assert len(pack) == 4
        assert pack["incident_digest"]["corpus"]["lines"] == 1
        assert pack["scan_signatures"]["zero"]
        assert pack["timeline"]["episodes"][0]["groups"][0][0] == "ERROR"
        assert pack["nearby_logs"]["rows"][0][:2] == ["app-01.log", 1]
        for _ in range(3):
            assert agent.step() is True
        assert not query_client.calls
        assert agent.step() is True
        assert len(query_client.calls) == 1
        helper_tools, helper_messages = query_client.calls[0]
        assert helper_tools == []
        assert helper_messages[-1] == {"role": "user", "content": "Count ERROR events"}
        assert "Hadoop" not in json.dumps(helper_messages)
        assert agent.step() is False
        evidence = [m for m in main_client.calls[-1][1] if m["role"] == "tool"]
        assert len(evidence) == 5
        assert all(json.loads(m["content"])["success"] for m in evidence)
        data = [json.loads(m["content"])["data"] for m in evidence]
        assert all("see" in result for result in data[:2])
        assert "episodes" in data[2] and "rows" in data[3]
        assert json.loads(evidence[-1]["content"])["data"]["rows"] == [[1]]
        assert agent.messages[-1]["content"] == "One error; cause remains uncertain."
    finally:
        backend.close()


def test_seed_once_retry_failed_section_and_retrieve_after_compaction(
    tmp_path: Path, app_logger: ApplicationLogger, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "app-records.log").write_text(
        "2026-10-01 00:00:00,000 SEVERE [t] journal: missing partition\n"
    )
    original = log_evidence.scan
    scans = []

    def fail_first(db: SQLiteLogs, custom: list[dict]) -> dict:
        scans.append(custom)
        if len(scans) == 1:
            raise ToolExecutionError("Signature scan timed out.")
        return original(db, custom)

    monkeypatch.setattr(log_evidence, "scan", fail_first)
    reply = ChatCompletionMessage(role="assistant", content="Investigated.")
    main = FakeClient([reply] * 12)
    helper = FakeClient([])
    with closing(SQLiteLogs(tmp_path)) as db:
        agent = build_agent(db, app_logger, main, helper, "Investigate")
        run_turn(agent, "Look into this incident.", tmp_path / "out")
        pack = json.loads(main.calls[0][1][1]["content"].removeprefix(log_preamble.PACK_PREFIX))
        assert "unavailable" in pack["scan_signatures"]
        assert pack["nearby_logs"]["pivots"][0]["reasons"] == ["first fatal", "earliest episode"]
        assert (
            "zero" in json.loads(agent.executor.execute("scan_signatures", {"custom": []}))["data"]
        )
        run_turn(agent, "What happened next?", tmp_path / "out")
        assert len(main.calls) == 2 and len(scans) == 2
        assert sum(log_preamble.PACK_PREFIX in str(m["content"]) for m in agent.messages) == 1
        assert [p.read_text() for p in (tmp_path / "out").iterdir()] == ["Investigated."] * 2

        agent.messages = agent.compaction(agent.messages, main, 1)
        assert all(log_preamble.PACK_PREFIX not in str(m["content"]) for m in agent.messages)
        result = agent.executor.execute("timeline", log_preamble.DEFAULT_CALLS["timeline"])
        assert json.loads(result)["data"]["episodes"]
        agent.reset()
        agent.add_user_message("Start another investigation")
        assert len(scans) == 3 and not helper.calls
        result = agent.executor.execute("scan_signatures", {"custom": []})
        assert "see" in json.loads(result)["data"]


def test_sample_pack_fits_fallback_and_shortened_sections_remain_retrievable(
    tmp_path: Path, app_logger: ApplicationLogger
) -> None:
    experiment = Path(__file__).resolve().parents[1] / "experimental"
    prompt = (experiment / "vfsb_subagent/system_main_agent.md").read_text()
    reply = ChatCompletionMessage(role="assistant", content="Sample handoff.")
    main, helper = FakeClient([reply]), FakeClient([])
    with closing(SQLiteLogs(experiment / "data/workspace")) as db:
        agent = build_agent(db, app_logger, main, helper, prompt)
        estimator = agent.token_estimator = TokenEstimator(encoding=None)
        run_turn(agent, "Investigate the incident and cite the evidence.", tmp_path / "out")
        assert len(main.calls) == 1 and not helper.calls
        tools, messages = main.calls[0]
        assert (
            estimator.next_request(messages, tools)
            < agent.context_budget * agent.compaction_threshold
        )
        pack = json.loads(messages[1]["content"].removeprefix(log_preamble.PACK_PREFIX))
        assert pack["nearby_logs"]["pivots"]
        for name in log_preamble.DEFAULT_CALLS:
            if pack[name].get("pack_omitted_rows"):
                data = json.loads(agent.executor.execute(name, log_preamble.DEFAULT_CALLS[name]))[
                    "data"
                ]
                assert "see" not in data and "pack_omitted_rows" not in data
        for episode in pack["timeline"].get("episodes", []):
            for row in episode["groups"]:
                if isinstance(row[-1], dict):
                    source = row[-1]["see"]
                    if source == "nearby_logs":
                        refs = {f"{r[0]}:{r[1]}" for r in pack[source]["rows"]}
                    else:
                        refs = {r[-2] for r in pack[source]["rows"]}
                    assert row[-2] in refs
        agent.reset()
        with pytest.raises(UnexpectedResponseError, match="context threshold"):
            agent.add_user_message("oversized question " * 2000)
        assert len(agent.messages) == 1 and len(main.calls) == 1
