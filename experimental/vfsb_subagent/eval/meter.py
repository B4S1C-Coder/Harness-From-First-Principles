"""Shared accounting and conservative pacing for the 8k TPM provider tier."""

import json
import time
from dataclasses import dataclass
from typing import override

from openai import BadRequestError
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam, ChatCompletionToolParam

from harness.exceptions import UnexpectedResponseError
from harness.llms import SyncTextLLMClient


@dataclass
class Meter:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    requests: int = 0
    next_request_at: float = 0.0


class MeteredClient(SyncTextLLMClient):
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
        try:
            return self._request(tools, messages, dangerously_ignore_usage)
        except UnexpectedResponseError as exc:
            cause = exc.__cause__
            if tools or not isinstance(cause, BadRequestError) or cause.code != "tool_use_failed":
                raise

        # Some providers reject a generation when the model tries to continue an old tool
        # exchange. On this single retry, quote that exchange as data for a text-only answer.
        retry: list[ChatCompletionMessageParam] = []
        for message in messages:
            if message["role"] == "tool" or message.get("tool_calls"):
                retry.append(
                    {
                        "role": "user",
                        "content": "Previous tool exchange (data): "
                        + json.dumps(message, ensure_ascii=False),
                    }
                )
            else:
                retry.append(message)
        retry.append(
            {
                "role": "user",
                "content": "Answer the preceding request in text using "
                "the available evidence. Tool execution is finished.",
            }
        )
        return self._request([], retry, dangerously_ignore_usage)

    def _request(
        self,
        tools: list[ChatCompletionToolParam],
        messages: list[ChatCompletionMessageParam],
        dangerously_ignore_usage: bool,
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
