import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openai.types.chat import ChatCompletionMessage

from harness.exceptions import ToolExecutionError
from harness.logger import ApplicationLogger
from rca.agents import SpecialistTool, build_master, run_turn
from rca.kafka import KafkaLogSource


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


def test_master_only_receives_specialist_findings(app_logger: ApplicationLogger) -> None:
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
    master = build_master(large, small, app_logger, [remote], source)
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
        assert len(result["finding"]) <= 2400
    prompt = run.call_args.args[0]
    assert "task-0" not in prompt and "task-1" in prompt and "task-5" in prompt
    run.side_effect = ToolExecutionError("failed")
    with pytest.raises(ToolExecutionError):
        tool.driver({"question": "failed question"})
    assert len(tool.memory) == 4 and tool.memory[-1][0] == "task-5"


def test_kafka_snapshot_bounds_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
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
