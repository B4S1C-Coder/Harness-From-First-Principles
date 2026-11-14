import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletionMessage

from experimental.vfsb_subagent.log_backend import SQLiteLogs
from experimental.vfsb_subagent.log_tools import SearchLogsTool
from harness.exceptions import UnexpectedResponseError, ValueValidationError
from harness.llms import SyncTextLLMClient
from harness.logger import ApplicationLogger
from harness.shortcuts.generic_scmt import SCMTTAgent, SCMTTConfig


class FakeClient:
    def __init__(self, responses: list[ChatCompletionMessage]) -> None:
        self.responses = iter(responses)
        self.calls = []

    def generate_next(self, tools: list, messages: list) -> tuple:
        self.calls.append((list(tools), list(messages)))
        return SimpleNamespace(choices=[SimpleNamespace(message=next(self.responses))]), 10, 0


def search_call(arguments: str | None = None) -> ChatCompletionMessage:
    return ChatCompletionMessage(
        role="assistant",
        tool_calls=[
            {
                "id": "search-1",
                "type": "function",
                "function": {
                    "name": "search_logs",
                    "arguments": arguments
                    if arguments is not None
                    else json.dumps(
                        dict.fromkeys(["start", "end", "level", "filename", "keyword"])
                    ),
                },
            }
        ],
    )


def make_agent(
    client: FakeClient, logger: ApplicationLogger, backend: SQLiteLogs, limit: int | None = 1
) -> SCMTTAgent:
    return SCMTTAgent(
        client,
        logger,
        "Investigate",
        max_tool_turns=limit,
        enable_context_check=False,
        config=SCMTTConfig([SearchLogsTool(backend)]),
    )


def test_budget_forces_summary_and_logs_search(
    tmp_path: Path, app_logger: ApplicationLogger, log_dir: Path
) -> None:
    (tmp_path / "app-01.log").write_text("2025-01-01 00:00:00,000 ERROR [t] app: failed\n")
    backend = SQLiteLogs(tmp_path)
    try:
        client = FakeClient(
            [
                search_call(),
                ChatCompletionMessage(
                    role="assistant", content="Found a failure at app-01.log:1; cause is uncertain."
                ),
                search_call(),
            ]
        )
        agent = make_agent(client, app_logger, backend)
        agent.add_user_message("Investigate failure")
        assert agent.step() is True
        assert agent.step() is False
        assert client.calls[0][0]
        assert client.calls[1][0] == []
        assert "budget is exhausted" in client.calls[1][1][-1]["content"]
        assert any(m["role"] == "tool" for m in client.calls[1][1])
        assert agent.messages[-1]["content"].startswith("Found a failure")
        assert not any("budget is exhausted" in str(m) for m in agent.messages)
        agent.add_user_message("Follow up")
        assert agent.step() is True
        assert client.calls[2][0]
        agent.reset()
        assert agent._tool_turns == 0
    finally:
        backend.close()
    app_logger.close()
    lines = (log_dir / "application.log").read_text().splitlines()
    records = [line for line in lines if "Tool request:" in line or "Tool result:" in line]
    assert all("DEBUG" in line for line in records)
    request = json.loads(records[0].split("Tool request: ", 1)[1])
    result = json.loads(records[1].split("Tool result: ", 1)[1])
    assert request["call_id"] == result["call_id"] == "search-1"
    assert json.loads(request["arguments"])["keyword"] is None
    assert result["success"] and result["row_count"] == 1 and not result["truncated"]
    assert result["source_references"] == [{"filename": "app-01.log", "line": 1}]


@pytest.mark.parametrize("arguments", ["{", "{}"])
def test_failed_search_is_logged_and_counts_toward_budget(
    tmp_path: Path,
    app_logger: ApplicationLogger,
    log_dir: Path,
    arguments: str,
) -> None:
    backend = SQLiteLogs(tmp_path)
    try:
        client = FakeClient(
            [
                search_call(arguments),
                ChatCompletionMessage(role="assistant", content="No usable evidence yet."),
            ]
        )
        agent = make_agent(client, app_logger, backend)
        assert agent.step() is True
        assert agent.step() is False
        assert client.calls[-1][0] == []
    finally:
        backend.close()
    app_logger.close()
    result_line = next(
        line
        for line in (log_dir / "application.log").read_text().splitlines()
        if "Tool result:" in line
    )
    result = json.loads(result_line.split("Tool result: ", 1)[1])
    assert result["success"] is False and result["error"]
    assert "DEBUG" in result_line


@pytest.mark.parametrize(
    "response", [search_call(), ChatCompletionMessage(role="assistant", content="")]
)
def test_final_turn_cannot_execute_tools(
    tmp_path: Path, app_logger: ApplicationLogger, response: ChatCompletionMessage
) -> None:
    backend = SQLiteLogs(tmp_path)
    try:
        agent = make_agent(FakeClient([response]), app_logger, backend, limit=0)
        original = list(agent.messages)
        with pytest.raises(UnexpectedResponseError, match="final summary"):
            agent.step()
        assert agent.messages == original
    finally:
        backend.close()


def test_early_conclusion_and_invalid_limit(tmp_path: Path, app_logger: ApplicationLogger) -> None:
    backend = SQLiteLogs(tmp_path)
    try:
        client = FakeClient([ChatCompletionMessage(role="assistant", content="Conclusion")])
        agent = make_agent(client, app_logger, backend)
        assert agent.step() is False
        assert len(client.calls) == 1 and client.calls[0][0]
        with pytest.raises(ValueValidationError):
            make_agent(client, app_logger, backend, limit=-1)
    finally:
        backend.close()


def test_empty_tools_disable_provider_tool_choice() -> None:
    """Stub the SDK method itself: no HTTP client or provider request is constructed."""
    calls = []

    def create(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1, prompt_tokens_details=None))

    client = SyncTextLLMClient.__new__(SyncTextLLMClient)
    client.model = "fake"
    client._SyncTextLLMClient__client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    client.generate_next([], [])
    import openai

    assert calls[0]["tools"] is openai.omit
    assert calls[0]["tool_choice"] == "none"
    definitions = [{"type": "function", "function": {"name": "test"}}]
    client.generate_next(definitions, [])
    assert calls[1]["tools"] == definitions and calls[1]["tool_choice"] == "auto"
