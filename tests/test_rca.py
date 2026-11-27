import json
from pathlib import Path
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openai.types.chat import ChatCompletionMessage

from harness.exceptions import ConfigurationError, ToolExecutionError, UnexpectedResponseError
from harness.log.investigator import InvestigationAgent
from harness.log.log_backend import SQLiteLogs
from harness.prompts import PromptStore
from harness.logger import ApplicationLogger
from rca.agents import SpecialistTool, build_master, build_log_agent, run_turn
from rca.config import RCAConfig, CONTEXT_BUDGET
from rca.prompts import Prompts, load_prompts, prompt_store, register


def reply(content: str = "", *, tool: str = "", args: dict | None = None) -> tuple:
    message = ChatCompletionMessage(role="assistant", content=content or None)
    if tool:
        message = ChatCompletionMessage.model_validate(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tool,
                        "type": "function",
                        "function": {"name": tool, "arguments": json.dumps(args)},
                    }
                ],
            }
        )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)]), 1, 0


@pytest.fixture
def prompts(tmp_path: Path) -> Prompts:
    with prompt_store(tmp_path / "rca.db"):
        register()
        return load_prompts()


def test_master_only_receives_specialist_findings(
    app_logger: ApplicationLogger, prompts: Prompts
) -> None:
    source, large, small = Mock(), Mock(), Mock()
    source.lines.return_value = [("partition", "2026-01-01 12:00:00,123 WARN [t] api: private-row")]
    large.generate_next.side_effect = [
        reply(tool="analyze_logs", args={"question": "Trace request"}),
        reply(tool="incident_digest", args=dict.fromkeys(["start", "end", "level", "filename"])),
        reply("Route mismatch at partition:1"),
        reply(tool="research_mcp", args={"question": "Verify route ordering"}),
        reply("Investigation complete"),
    ]
    small.generate_next.side_effect = [
        reply(tool="context7__query-docs", args={"question": "routing"}),
        reply("First matching route wins"),
    ]
    remote = SpecialistTool("context7__query-docs", "Test fixture", lambda _: "private-doc")
    master = build_master(large, large, small, app_logger, [remote], source, prompts, RCAConfig())
    assert run_turn(master, "Investigate") == "Investigation complete"
    assert set(master.executor.definitions()) == {"analyze_logs", "research_mcp"}
    history = json.dumps(master.messages)
    assert "Route mismatch at partition:1" in history and "First matching route wins" in history
    assert "private-row" not in history and "private-doc" not in history
    assert "private-row" in str(large.generate_next.call_args_list[2])
    assert "private-doc" in str(small.generate_next.call_args)
    assert "private-row" not in str(small.generate_next.call_args)


def test_specialist_memory_remembers_only_recent_bounded_handoffs() -> None:
    run = Mock(return_value="a" * 4000)
    tool = SpecialistTool("specialist", "test", run)
    for i in range(6):
        result = tool.driver({"question": f"task-{i}"})
        assert len(result["finding"]) <= RCAConfig.finding_bytes
    prompt = run.call_args.args[0]
    assert "task-0" not in prompt and "task-1" in prompt and "task-5" in prompt
    run.side_effect = ToolExecutionError("failed")
    with pytest.raises(ToolExecutionError):
        tool.driver({"question": "failed question"})
    assert len(tool.memory) == 4 and tool.memory[-1][0] == "task-5"


def test_kafka_snapshot_bounds_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("confluent_kafka")
    from rca.kafka import KafkaLogSource

    consumer = Mock()
    factory = Mock(return_value=consumer)
    monkeypatch.setattr("rca.kafka.Consumer", factory)
    consumer.list_topics.return_value.topics = {
        "app-logs": SimpleNamespace(error=None, partitions={0: None, 1: None, 2: None})
    }
    consumer.get_watermark_offsets.side_effect = [(0, 5), (8, 8), (12, 13)]
    records = []
    for part, offset, value in [(0, 3, b"first"), (2, 12, b"second"), (0, 4, b"third")]:
        record = Mock()
        record.partition.return_value = part
        record.offset.return_value = offset
        record.error.return_value = None
        record.value.return_value = value
        records.append(record)
    consumer.poll.side_effect = records
    assert list(KafkaLogSource(offsets_per_partition=2).lines()) == [
        ("app-logs[0]@3", "first"),
        ("app-logs[2]@12", "second"),
        ("app-logs[0]@3", "third"),
    ]
    assert [(tp.partition, tp.offset) for tp in consumer.assign.call_args.args[0]] == [
        (0, 3),
        (2, 12),
    ]
    assert factory.call_args.args[0]["enable.auto.commit"] is False
    consumer.close.assert_called_once()
    consumer.list_topics.return_value.topics = {}
    with pytest.raises(ToolExecutionError, match="unavailable"):
        list(KafkaLogSource().lines())
    assert consumer.close.call_count == 2


def test_config_defaults_and_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {
        "RCA_MASTER_MODEL": "master",
        "RCA_LOG_MODEL": "investigator",
        "RCA_RESEARCH_MODEL": "research",
        "RCA_MASTER_MAX_TOOL_TURNS": "3",
        "RCA_LOG_MAX_TOOL_TURNS": "2",
        "RCA_RESEARCH_MAX_TOOL_TURNS": "1",
        "RCA_FINDING_BYTES": "800",
        "RCA_MEMORY_SIZE": "2",
        "KAFKA_BOOTSTRAP_SERVERS": "broker:29092",
        "KAFKA_LOG_TOPIC": "other",
        "KAFKA_OFFSETS_PER_PARTITION": "80",
    }
    for key in env:
        monkeypatch.delenv(key, raising=False)
    assert RCAConfig.from_env() == RCAConfig()
    assert CONTEXT_BUDGET == 8000
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert RCAConfig.from_env() == RCAConfig(
        "master", "investigator", "research", 3, 2, 1, 800, 2, "broker:29092", "other", 80
    )
    monkeypatch.setenv("RCA_FINDING_BYTES", "8000")
    with pytest.raises(ConfigurationError, match="RCA_FINDING_BYTES"):
        RCAConfig.from_env()


def test_registration_preserves_existing_key_and_reports_missing(tmp_path: Path) -> None:
    database = tmp_path / "prompts.db"
    with prompt_store(database):
        PromptStore.add_prompt("rca.master.system", "Custom instructions")
        with pytest.raises(ConfigurationError, match=r"rca.logs.system.*python -m rca.prompts"):
            load_prompts()
        register()
        register()
    with prompt_store(database):
        assert load_prompts().master == "Custom instructions"
        for role in ("master", "logs", "research"):
            with pytest.raises(LookupError):
                PromptStore.load_prompt(f"rca.{role}.system", version=2)


def test_investigator_opening_and_empty_report(
    app_logger: ApplicationLogger, prompts: Prompts
) -> None:
    source, client = Mock(), Mock()
    source.lines.return_value = [
        ("partition", f"2026-01-01 12:00:00,123 WARN [t] api: request=ABC symptom {i}")
        for i in range(150)
    ]
    client.generate_next.return_value = reply("   ")
    with closing(SQLiteLogs(source)) as db:
        agent = build_log_agent(
            client, app_logger, db, prompts.logs, RCAConfig(log_max_tool_turns=2)
        )
        assert isinstance(agent, InvestigationAgent)
        assert agent.context_budget == 8000 and agent.max_tool_turns == 2
        assert set(agent.executor.definitions()) == {
            "incident_digest",
            "scan_signatures",
            "timeline",
            "search_logs",
            "nearby_logs",
        }
        with pytest.raises(UnexpectedResponseError, match="Empty report"):
            run_turn(agent, "Why did request ABC fail?")
        tools, messages = client.generate_next.call_args.args
        assert messages[1] is agent.opening_message
        assert "request=ABC" in messages[1]["content"]
        assert messages[2]["content"] == "Why did request ABC fail?"
        assert agent.token_estimator.next_request(messages[:3], tools) < 6400


def test_budget_for_master_and_research(
    app_logger: ApplicationLogger, prompts: Prompts, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rca.agents as agents

    built = []
    constructor = agents.ReportingAgent

    def capture(**kwargs: object) -> agents.ReportingAgent:
        instance = constructor(**kwargs)
        built.append(instance)
        return instance

    monkeypatch.setattr(agents, "ReportingAgent", capture)
    research = Mock()
    research.generate_next.return_value = reply("x" * 4000)
    config = RCAConfig(finding_bytes=1800, master_max_tool_turns=4, research_max_tool_turns=3)
    primary, logs, source = Mock(), Mock(), Mock()
    source.lines.return_value = []
    logs.generate_next.return_value = reply("y" * 4000)
    question = "q" * 2000
    primary.generate_next.side_effect = [
        reply(tool="analyze_logs", args={"question": question}),
        reply(tool="research_mcp", args={"question": question}),
        reply("Finished"),
    ]
    master = build_master(primary, logs, research, app_logger, [], source, prompts, config)
    assert run_turn(master, question) == "Finished"
    assert [a.context_budget for a in built] == [8000, 8000]
    assert [a.max_tool_turns for a in built] == [4, 3]
    findings = [
        json.loads(m["content"])["data"]["finding"] for m in master.messages if m["role"] == "tool"
    ]
    assert [len(f.encode()) for f in findings] == [1800, 1800]
    assert master.token_estimator.next_request(master.messages, master.tools) < 6400
