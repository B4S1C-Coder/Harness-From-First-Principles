import json

from abc import ABC, abstractmethod
from contextlib import contextmanager
from collections.abc import Callable, Generator
from typing import cast, final

from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
    ChatCompletionMessage,
)

from harness.compaction import naive_compaction
from harness.exceptions import UnexpectedResponseError, ValueValidationError
from harness.llms import SyncTextLLMClient
from harness.logger import ApplicationLogger


class SynchronousAgentBase[ConfigT](ABC):
    @final
    def __init__(
        self,
        client: SyncTextLLMClient,
        logger: ApplicationLogger,
        system_prompt: str,
        *,
        config: ConfigT | None = None,
        tools: list[ChatCompletionToolParam] | None = None,
        context_budget: int = 8_000,
        compaction_threshold: float = 0.8,
        recent_turns_to_keep: int = 2,
        enable_context_check: bool = True,
        max_tool_turns: int | None = None,
        compaction: Callable[
            [list[ChatCompletionMessageParam], SyncTextLLMClient, int],
            list[ChatCompletionMessageParam],
        ] = naive_compaction,
    ) -> None:

        if max_tool_turns is not None and max_tool_turns < 0:
            raise ValueValidationError("max_tool_turns must be nonnegative or None.")
        self.max_tool_turns = max_tool_turns
        self._tool_turns = 0
        self.compaction = compaction
        self.enable_context_check = enable_context_check
        self.client = client
        self.logger = logger
        self.tools = tools if tools is not None else []

        self.context_budget = context_budget
        self.compaction_threshold = compaction_threshold
        self.recent_turns_to_keep = recent_turns_to_keep

        self.system_prompt = system_prompt
        self.messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
        ]

        self.post_init(config)

    @abstractmethod
    def post_init(self, config: ConfigT | None) -> None:
        """Optional subclass initialization hook"""
        return None

    @abstractmethod
    def handle_message(self, message: ChatCompletionMessage) -> bool:
        """
        Handle a normal assistant response.

        Return true to continue the current turn,
        False to end the current turn.
        """
        ...

    @abstractmethod
    def handle_tool_call(self, message: ChatCompletionMessage) -> bool:
        """
        Handle assistant tool calls.

        Return true to continue the current turn,
        False to end the current turn.
        """
        ...

    @contextmanager
    def turn(self) -> Generator[None]:
        """Establish a correlation scope for an entire agent turn."""
        with self.logger.correlation_scope():
            yield

    def add_user_message(self, content: str) -> None:
        """Add user input to conversation history."""
        if content:
            self._tool_turns = 0
            self.messages.append({"role": "user", "content": content})

    def step(self) -> bool:
        """
        Advance the agent by one LLM interaction.
        Returns whether the current turn should continue.
        """

        summarize = self.max_tool_turns is not None and self._tool_turns >= self.max_tool_turns
        request_tools = [] if summarize else self.tools

        def request_messages() -> list[ChatCompletionMessageParam]:
            if not summarize:
                return self.messages
            return [
                *self.messages,
                {
                    "role": "system",
                    "content": "The investigation tool-turn budget is exhausted. Return a final "
                    "summary now using only the evidence already gathered. Include findings and "
                    "source references, supported conclusions or hypotheses, uncertainty, and "
                    "unresolved questions. If no conclusion is supported, say so explicitly. "
                    "Do not request tools or invent evidence.",
                },
            ]

        # One UTF-8 byte per estimated token is intentionally conservative.
        def request_size() -> int:
            return len(
                json.dumps(
                    {"messages": request_messages(), "tools": request_tools}, ensure_ascii=False
                ).encode("utf-8")
            )

        threshold = self.context_budget * self.compaction_threshold
        if self.enable_context_check and request_size() >= threshold:
            try:
                self.messages = self.compaction(
                    self.messages, self.client, self.recent_turns_to_keep
                )
            except Exception as exc:
                raise UnexpectedResponseError("Compaction", "Unable to summarize history.") from exc
            if request_size() >= threshold:
                raise UnexpectedResponseError(
                    "Compaction", "Request remains above the context threshold."
                )

        self.logger.debug("Query sent to the model.")
        if summarize:
            self.logger.debug(
                "Tool-turn budget exhausted (%s); requesting final summary.", self.max_tool_turns
            )

        response, input_tokens, cached_tokens = self.client.generate_next(
            request_tools, request_messages()
        )

        self.logger.info(f"Input tok; {input_tokens}, Cached tok: {cached_tokens}")

        if not response.choices:
            raise UnexpectedResponseError(
                self.__class__.__qualname__, "No choices returned by LLM Provider."
            )

        assistant_message = response.choices[0].message
        if summarize and (assistant_message.tool_calls or not assistant_message.content):
            raise UnexpectedResponseError(
                self.__class__.__qualname__, "Expected a nonempty final summary without tool calls."
            )

        self.messages.append(
            cast(
                ChatCompletionAssistantMessageParam, assistant_message.model_dump(exclude_none=True)
            )
        )

        if assistant_message.tool_calls:
            self._tool_turns += 1
            should_continue = self.handle_tool_call(assistant_message)
        else:
            should_continue = self.handle_message(assistant_message)

        return False if summarize else should_continue

    def reset(self) -> None:
        """Reset conversation history while retaining agent configuration."""
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self._tool_turns = 0
