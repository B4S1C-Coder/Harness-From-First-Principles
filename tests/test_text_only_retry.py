from copy import deepcopy
from unittest.mock import Mock

from openai import BadRequestError
import pytest

from harness.exceptions import UnexpectedResponseError
from harness.llms import SyncTextLLMClient, TextOnlyRetryClient


def bad_request(code: str) -> BadRequestError:
    return BadRequestError("Rejected", response=Mock(status_code=400), body={"code": code})


@pytest.mark.parametrize("wrapped", [False, True])
def test_text_only_retry(wrapped: bool) -> None:
    client = Mock()
    raw = bad_request("tool_use_failed")
    failure = UnexpectedResponseError("provider") if wrapped else raw
    if wrapped:
        failure.__cause__ = raw
    result = (Mock(), 17, 3)
    client.generate_next.side_effect = [failure, result]
    messages = [
        {"role": "user", "content": "Summarize"},
        {"role": "assistant", "tool_calls": [{"id": "q"}]},
        {"role": "tool", "tool_call_id": "q", "content": "source observation"},
    ]
    original = deepcopy(messages)
    assert (
        TextOnlyRetryClient(client).generate_next([], messages, dangerously_ignore_usage=True)
        is result
    )
    first, second = client.generate_next.call_args_list
    assert first.args == ([], original)
    tools, retry = second.args
    assert tools == [] and messages == original
    assert first.kwargs == second.kwargs == {"dangerously_ignore_usage": True}
    assert all(m["role"] != "tool" and "tool_calls" not in m for m in retry)
    assert retry[0] == messages[0] and "quoted data" in retry[1]["content"]
    assert "source observation" in retry[2]["content"] and "prose" in retry[-1]["content"]


@pytest.mark.parametrize(
    ("tools", "codes"),
    [
        ([{}], ["tool_use_failed"]),
        ([], ["other_400"]),
        ([], ["tool_use_failed", "tool_use_failed"]),
    ],
)
def test_failure_propagates(tools: list, codes: list[str]) -> None:
    client = Mock()
    errors = [bad_request(code) for code in codes]
    client.generate_next.side_effect = errors
    with pytest.raises(UnexpectedResponseError) as caught:
        TextOnlyRetryClient(client).generate_next(tools, [])
    assert caught.value.__cause__ is errors[-1]
    assert client.generate_next.call_count == len(errors)


def test_sync_client_interface() -> None:
    provider = Mock(spec=SyncTextLLMClient)
    provider.model = "first"
    client = TextOnlyRetryClient(provider)
    assert isinstance(client, SyncTextLLMClient)
    assert client.model == "first"
    client.model = "second"
    assert provider.model == "second"
    assert client.check_connection() is provider.check_connection.return_value
    error = bad_request("invalid_request")
    provider.check_connection.side_effect = error
    with pytest.raises(UnexpectedResponseError) as caught:
        client.check_connection()
    assert caught.value.__cause__ is error
