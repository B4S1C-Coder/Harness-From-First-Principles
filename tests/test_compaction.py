from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletionMessage

from harness.agents import SynchronousAgentBase
from harness.compaction import SUMMARY_PREFIX, tool_aware_compaction
from harness.exceptions import UnexpectedResponseError


class FakeClient:
    def __init__(self, content: str | None = "Findings and source app-01.log:1") -> None:
        self.content = content
        self.calls = []

    def generate_next(self, tools: list, messages: list) -> tuple:
        self.calls.append((tools, list(messages)))
        return (
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=ChatCompletionMessage(role="assistant", content=self.content)
                    )
                ]
            ),
            99999,
            0,
        )


def history() -> list:
    messages = [
        {"role": "system", "content": "Original instructions"},
        {"role": "user", "content": "Investigate the incident"},
    ]
    for n in range(4):
        messages += [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": f"{n}a",
                        "type": "function",
                        "function": {"name": "search", "arguments": "{}"},
                    },
                    {
                        "id": f"{n}b",
                        "type": "function",
                        "function": {"name": "search", "arguments": "{}"},
                    },
                ],
            },
            {"role": "tool", "tool_call_id": f"{n}a", "content": "evidence " * 500},
            {"role": "tool", "tool_call_id": f"{n}b", "content": "other"},
        ]
    return messages


def test_intra_turn_compaction_and_repeated_summary() -> None:
    original = history()
    client = FakeClient()
    compacted = tool_aware_compaction(original, client, 1)
    assert compacted[0] == original[0] and original[1] in compacted
    assert compacted[-3:] == original[-3:]
    assert len(client.calls) > 1
    assert all(len(str(messages).encode()) < 6000 for _, messages in client.calls)
    compacted += [{"role": "assistant", "content": "final"}]
    repeated = tool_aware_compaction(compacted, client, 1)
    assert repeated[-1]["content"] == "final"
    assert sum(str(m.get("content", "")).startswith(SUMMARY_PREFIX) for m in repeated) == 1


def test_incomplete_batch_and_empty_summary() -> None:
    original = history()[:-1]
    result = tool_aware_compaction(original, FakeClient(), 0)
    assert result[-2:] == original[-2:]
    with pytest.raises(UnexpectedResponseError):
        tool_aware_compaction(history(), FakeClient(None), 1)


class Agent(SynchronousAgentBase[None]):
    def post_init(self, config: None) -> None:
        pass

    def handle_message(self, message: ChatCompletionMessage) -> bool:
        return False

    def handle_tool_call(self, message: ChatCompletionMessage) -> bool:
        return True


def test_preflight_and_final_report(app_logger) -> None:
    client = FakeClient("final report")
    seen = []

    def compact(messages: list, llm_client: FakeClient, keep: int) -> list:
        assert not client.calls
        seen.append(True)
        return messages[:2]

    agent = Agent(client, app_logger, "system", context_budget=1000, compaction=compact)
    agent.add_user_message("request")
    agent.messages.append({"role": "assistant", "content": "x" * 2000})
    assert agent.step() is False
    assert seen and len(client.calls) == 1
    assert agent.messages[-1]["content"] == "final report"


@pytest.mark.parametrize("failure", [False, True])
def test_preflight_blocks_oversized_request(app_logger, failure: bool) -> None:
    client = FakeClient()

    def compact(messages: list, llm_client: FakeClient, keep: int) -> list:
        if failure:
            raise UnexpectedResponseError("fake")
        return messages

    agent = Agent(client, app_logger, "x" * 1000, context_budget=100, compaction=compact)
    with pytest.raises(UnexpectedResponseError):
        agent.step()
    assert not client.calls


def test_tool_handler_result_and_tool_schema_budget(app_logger) -> None:
    class ToolClient(FakeClient):
        def generate_next(self, tools: list, messages: list) -> tuple:
            response, tokens, cached = super().generate_next(tools, messages)
            response.choices[0].message = ChatCompletionMessage(
                role="assistant",
                tool_calls=[
                    {
                        "id": "a",
                        "type": "function",
                        "function": {"name": "search", "arguments": "{}"},
                    }
                ],
            )
            return response, tokens, cached

    client = ToolClient()
    agent = Agent(client, app_logger, "system")
    assert agent.step() is True
    assert agent.messages[-1]["tool_calls"][0]["id"] == "a"
    blocked = Agent(
        FakeClient(), app_logger, "system", tools=[{"large": "x" * 1000}], context_budget=100
    )
    with pytest.raises(UnexpectedResponseError):
        blocked.step()
    assert not blocked.client.calls
