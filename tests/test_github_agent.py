import json
from unittest.mock import Mock

from openai.types.chat import ChatCompletionMessage
import pytest

from experimental.github_agent import run
from harness.exceptions import EnvVarNotSetError
from harness.logger import ApplicationLogger
from harness.mcp import ServerConfig, load_mcp_config
from harness.mcp.http_client import HTTPClient


def test_config_requires_github_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(EnvVarNotSetError, match="GITHUB_TOKEN"):
        load_mcp_config(run.HERE / "servers.json")


def test_issue_turn(
    monkeypatch: pytest.MonkeyPatch,
    app_logger: ApplicationLogger,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-pat")
    monkeypatch.setattr(run, "load_dotenv", Mock())
    monkeypatch.setattr(run, "ApplicationLogger", Mock(return_value=app_logger))
    questions = iter(["Summarize example/repo#1", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(questions))
    transport = Mock(spec=HTTPClient)

    def connect(name: str, config: ServerConfig) -> Mock:
        assert config.url == "https://api.githubcopilot.com/mcp/"
        assert config.headers["Authorization"] == "Bearer dummy-pat"
        transport.name = name
        transport.config = config
        return transport

    monkeypatch.setattr("harness.mcp.runtime.HTTPClient", connect)
    transport.request.side_effect = [
        {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}},
        {"tools": [{"name": "issue_read"}, {"name": "issue_write"}]},
        {"content": [{"type": "text", "text": "example result"}]},
    ]
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
    llm.generate_next.side_effect = [
        (Mock(choices=[Mock(message=m)]), 100, 0) for m in (call, answer)
    ]
    run.main()
    transport.request.assert_any_call("tools/call", {"name": "issue_read", "arguments": args})
    transport.close.assert_called_once()
    assert "Summary of comments" in capsys.readouterr().out
