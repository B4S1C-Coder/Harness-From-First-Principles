from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletionMessage

from harness.agents import SynchronousAgentBase
from harness.token_estimator import TokenEstimator


class FourCharEncoding:
    """Deterministic stand-in for a tokenizer: one token per four characters."""

    def encode(self, text: str, disallowed_special: tuple = ()) -> list[int]:
        return [0] * (len(text) // 4)


@pytest.fixture
def estimator() -> TokenEstimator:
    estimator = TokenEstimator(encoding=None)
    estimator._enc = FourCharEncoding()
    return estimator


def test_fallback_without_tokenizer() -> None:
    estimator = TokenEstimator(encoding=None, fallback_bytes_per_token=2.0)
    assert not estimator.has_tokenizer
    assert estimator.count("x" * 100) == 51
    assert TokenEstimator(encoding="no-such-encoding").has_tokenizer is False


def test_message_counts_content_tool_calls_and_reasoning(estimator: TokenEstimator) -> None:
    call = {"function": {"name": "search_logs", "arguments": '{"keyword": "x"}'}}
    assert estimator.message({"content": "a" * 40}) == estimator.PER_MESSAGE + 10
    # "search_logs" + '{"keyword": "x"}' is 27 characters, i.e. 6 stub tokens.
    assert estimator.message({"tool_calls": [call]}) == estimator.PER_MESSAGE + 6
    assert estimator.message({"content": "a" * 40, "reasoning": "b" * 40}) == (
        estimator.PER_MESSAGE + 20
    )


def test_first_request_is_padded_and_includes_tools(estimator: TokenEstimator) -> None:
    messages = [{"role": "system", "content": "s" * 400}]
    tools = [{"name": "t" * 400}]
    raw = estimator.message(messages[0]) + estimator.count('[{"name": "' + "t" * 400 + '"}]')
    assert estimator.next_request(messages, tools) == int(raw * estimator.FIRST_REQUEST_MARGIN)


def test_later_requests_trust_provider_and_count_only_new_messages(
    estimator: TokenEstimator,
) -> None:
    messages = [{"role": "user", "content": "q" * 4000}] * 3 + [
        {"role": "tool", "content": "r" * 400}
    ]
    # Three messages were already inside the 7450 prompt tokens the provider reported.
    assert estimator.next_request(messages, last_prompt_tokens=7450, counted=3) == (
        7450 + estimator.PER_MESSAGE + 100
    )


def test_real_tokenizer_if_available() -> None:
    estimator = TokenEstimator()
    if not estimator.has_tokenizer:
        pytest.skip("tiktoken o200k_harmony not installed or vocabulary not downloadable")
    assert 0 < estimator.count("hello world") <= 4
    assert estimator.count("x" * 1000) < 1000
    assert estimator.count("<|endoftext|> in a log line") > 0  # special-token text must not raise


class TokenClient:
    def __init__(self, prompt_tokens: list[int]) -> None:
        self.prompt_tokens = list(prompt_tokens)

    def generate_next(self, tools: list, messages: list) -> tuple:
        message = ChatCompletionMessage(role="assistant", content="ok")
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        return response, self.prompt_tokens.pop(0), 0


class Agent(SynchronousAgentBase[None]):
    def post_init(self, config: None) -> None:
        pass

    def handle_message(self, message: ChatCompletionMessage) -> bool:
        return False

    def handle_tool_call(self, message: ChatCompletionMessage) -> bool:
        return True


def test_agent_compacts_on_provider_usage_not_serialized_bytes(
    app_logger, estimator: TokenEstimator
) -> None:
    compactions = []

    def compact(messages: list, llm_client: object, keep: int) -> list:
        compactions.append(len(messages))
        return messages[:2]

    agent = Agent(
        TokenClient([900, 120]),
        app_logger,
        "system",
        context_budget=1000,
        compaction_threshold=0.8,
        compaction=compact,
        token_estimator=estimator,
    )
    agent.add_user_message("investigate")
    assert agent.step() is False  # first request: small padded estimate, no compaction
    assert not compactions and agent._last_prompt_tokens == 900

    # The history is only a few hundred bytes, but the provider said the prompt was 900 tokens.
    agent.add_user_message("continue")
    agent.step()
    assert compactions == [4]
    # Compaction rewrote history, so the provider figure was dropped and then replaced by the
    # one reported for the compacted request.
    assert agent._last_prompt_tokens == 120


def test_zero_usage_is_unknown_and_reset_clears_state(app_logger, estimator) -> None:
    agent = Agent(TokenClient([0]), app_logger, "system", token_estimator=estimator)
    agent.add_user_message("hi")
    agent.step()
    assert agent._last_prompt_tokens is None
    agent._last_prompt_tokens, agent._sent_message_count = 5, 3
    agent.reset()
    assert agent._last_prompt_tokens is None and agent._sent_message_count == 0
