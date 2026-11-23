"""Shared accounting and conservative pacing for the 8k TPM provider tier."""

import time
from dataclasses import dataclass
from typing import override

from openai.types.chat import ChatCompletion, ChatCompletionMessageParam, ChatCompletionToolParam

from harness.llms import SyncTextLLMClient, TextOnlyRetryClient


@dataclass
class Meter:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    requests: int = 0
    next_request_at: float = 0.0


class _PacedClient(SyncTextLLMClient):
    def __init__(self, model: str, meter: Meter) -> None:
        super().__init__(model=model, max_retries=8)
        self.meter = meter

    @override
    def generate_next(
        self,
        tools: list[ChatCompletionToolParam],
        messages: list[ChatCompletionMessageParam],
        *,
        dangerously_ignore_usage: bool = False,
    ) -> tuple[ChatCompletion, int, int]:
        # Output size is unknown in advance. Give each call the entire minute's allowance.
        delay = self.meter.next_request_at - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self.meter.requests += 1
        try:
            response, prompt, cached = super().generate_next(
                tools, messages, dangerously_ignore_usage=dangerously_ignore_usage
            )
        finally:
            self.meter.next_request_at = time.monotonic() + 60
        self.meter.prompt_tokens += prompt
        if response.usage is not None:
            self.meter.completion_tokens += response.usage.completion_tokens
        return response, prompt, cached


class MeteredClient(TextOnlyRetryClient):
    def __init__(self, model: str, meter: Meter) -> None:
        super().__init__(_PacedClient(model, meter))
