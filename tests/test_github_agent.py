import json
from unittest.mock import Mock

from openai import BadRequestError
from openai.types.chat import ChatCompletionMessage
import pytest

from experimental.github_agent import run
from harness.exceptions import EnvVarNotSetError, UnexpectedResponseError
from harness.logger import ApplicationLogger
from harness.mcp import ServerConfig, load_mcp_config
from harness.mcp.http_client import HTTPClient


@pytest.mark.parametrize("missing", ["GITHUB_TOKEN", "CONTEXT7_API_KEY"])
def test_config_requires_credentials(monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-pat")
    monkeypatch.setenv("CONTEXT7_API_KEY", "dummy-context7")
    monkeypatch.delenv(missing)
    with pytest.raises(EnvVarNotSetError, match=missing):
        load_mcp_config(run.ROOT / "servers.json")


@pytest.mark.parametrize("summary", ["unused", "retry", "reset"])
def test_issue_turn(
    summary: str,
    monkeypatch: pytest.MonkeyPatch,
    app_logger: ApplicationLogger,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-pat")
    monkeypatch.setenv("CONTEXT7_API_KEY", "dummy-context7")
    monkeypatch.setattr(run, "load_dotenv", Mock())
    monkeypatch.setattr(run, "ApplicationLogger", Mock(return_value=app_logger))
    questions = iter(
        (["first failed query"] if summary != "unused" else [])
        + ["Summarize example/repo#1", "quit"]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(questions))
    transport = Mock(spec=HTTPClient)

    docs = Mock(spec=HTTPClient)
    docs.request.side_effect = [
        {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}},
        {"tools": [{"name": "resolve-library-id"}, {"name": "query-docs"}]},
    ]

    def connect(name: str, config: ServerConfig) -> Mock:
        if name == "context7":
            assert config.url == "https://mcp.context7.com/mcp"
            assert config.headers == {"Authorization": "Bearer dummy-context7"}
            docs.name = name
            docs.config = config
            return docs
        assert config.url == "https://api.githubcopilot.com/mcp/"
        assert config.headers["Authorization"] == "Bearer dummy-pat"
        transport.name = name
        transport.config = config
        return transport

    monkeypatch.setattr("harness.mcp.runtime.HTTPClient", connect)
    transport.request.side_effect = [
        {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}},
        {"tools": [{"name": "issue_read"}, {"name": "issue_write"}, {"name": "search_issues"}]},
    ] + [{"content": [{"type": "text", "text": "example result"}]}] * (
        4 if summary != "unused" else 1
    )
    llm = Mock()
    monkeypatch.setattr(run, "SyncTextLLMClient", Mock(return_value=llm))
    args = {"method": "get_comments", "owner": "example", "repo": "repo", "issue_number": 1}
    call = ChatCompletionMessage.model_validate(
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call",
                    "type": "function",
                    "function": {"name": "github__issue_read", "arguments": json.dumps(args)},
                }
            ],
        }
    )
    answer = ChatCompletionMessage(role="assistant", content="Summary of comments")
    tool_response = (Mock(choices=[Mock(message=call)]), 100, 0)
    responses = [tool_response, (Mock(choices=[Mock(message=answer)]), 100, 0)]
    if summary != "unused":
        rejection = UnexpectedResponseError("test provider", "HTTP 400")
        rejection.__cause__ = BadRequestError(
            "Tool choice is none, but model called a tool",
            response=Mock(status_code=400),
            body={"code": "tool_use_failed"},
        )
        retry_result = (
            rejection if summary == "reset" else (Mock(choices=[Mock(message=answer)]), 100, 0)
        )
        responses = [tool_response] * 3 + [rejection, retry_result] + responses
    llm.generate_next.side_effect = responses
    run.main()
    transport.request.assert_any_call("tools/call", {"name": "issue_read", "arguments": args})
    transport.close.assert_called_once()
    docs.close.assert_called_once()
    definitions = llm.generate_next.call_args_list[0].args[0]
    assert {tool["function"]["name"] for tool in definitions} == {
        "github__issue_read",
        "github__search_issues",
        "context7__resolve-library-id",
        "context7__query-docs",
    }
    if summary != "unused":
        calls = llm.generate_next.call_args_list
        assert len(calls) == 7
        assert calls[3].args[0] == calls[4].args[0] == [] and calls[5].args[0]
        second_turn = calls[5].args[1]
        assert any(m.get("content") == "first failed query" for m in second_turn) == (
            summary == "retry"
        )
    expected_answers = 2 if summary == "retry" else 1
    assert capsys.readouterr().out.count("Summary of comments") == expected_answers
