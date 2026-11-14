import json
from pathlib import Path
from types import SimpleNamespace

from openai.types.chat import ChatCompletionMessage

from experimental.vfsb_subagent.log_backend import SQLiteLogs
from experimental.vfsb_subagent.run import (
    build_agent,
    MAIN_AGENT_MAX_STEPS,
    MAIN_AGENT_MAX_TOOL_TURNS,
)
from harness.logger import ApplicationLogger


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
                        "function": {"name": "log_overview", "arguments": "{}"},
                    }
                ],
            ),
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
        assert {tool["function"]["name"] for tool in agent.tools} == {
            "log_overview",
            "search_logs",
            "nearby_logs",
            "advanced_log_analysis",
        }
        assert agent.max_tool_turns == MAIN_AGENT_MAX_TOOL_TURNS
        assert MAIN_AGENT_MAX_STEPS == MAIN_AGENT_MAX_TOOL_TURNS + 1
        assert not agent.enable_context_check
        agent.add_user_message("Investigate the Hadoop failure using your log-analysis specialist.")
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
        assert len(evidence) == 2
        assert json.loads(evidence[-1]["content"])["data"]["rows"] == [[1]]
        assert agent.messages[-1]["content"] == "One error; cause remains uncertain."
    finally:
        backend.close()
