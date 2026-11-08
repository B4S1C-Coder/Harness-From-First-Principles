from abc import ABC, abstractmethod
from contextlib import contextmanager
from collections.abc import Generator
from typing import cast, final

from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
    ChatCompletionMessage,
)

from harness.compaction import naive_compaction
from harness.exceptions import UnexpectedResponseError
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
        compaction_threshold: float = 0.1,
        recent_turns_to_keep: int  = 2,
    ) -> None:

        self.client = client
        self.logger = logger
        self.tools = tools if tools is not None else []

        self.context_budget = context_budget
        self.compaction_threshold = compaction_threshold
        self.recent_turns_to_keep = recent_turns_to_keep

        self.system_prompt = system_prompt
        self.messages: list[ChatCompletionMessageParam] = [
            { "role": "system", "content": system_prompt },
        ]

        self.post_init(config)

    @abstractmethod
    def post_init(self, config: ConfigT | None) -> None:
        """ Optional subclass initialization hook"""
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
        """ Establish a correlation scope for an entire agent turn. """
        with self.logger.correlation_scope():
            yield

    def add_user_message(self, content: str) -> None:
        """ Add user input to conversation history. """
        if content:
            self.messages.append({ "role": "user", "content": content })

    def step(self) -> bool:
        """
        Advance the agent by one LLM interaction.
        Returns whether the current turn should continue.
        """

        self.logger.debug("Query sent to the model.")

        response, input_tokens, cached_tokens = self.client.generate_next(
            self.tools, self.messages
        )

        self.logger.info(f"Input tok; {input_tokens}, Cached tok: {cached_tokens}")

        if not response.choices:
            raise UnexpectedResponseError(
                self.__class__.__qualname__, "No choices returned by LLM Provider."
            )

        assistant_message = response.choices[0].message

        self.messages.append(
            cast(
                ChatCompletionAssistantMessageParam,
                assistant_message.model_dump(exclude_none=True)
            )
        )

        if assistant_message.tool_calls:
            should_continue = self.handle_tool_call(assistant_message)
        else:
            should_continue = self.handle_message(assistant_message)

        if (
            not should_continue
            and input_tokens >= self.context_budget * self.compaction_threshold
        ):
            self.messages = naive_compaction(self.messages, self.client, self.recent_turns_to_keep)

        return should_continue

    def reset(self) -> None:
        """ Reset conversation history while retaining agent configuration. """
        self.messages = [
            { "role": "system", "content": self.system_prompt }
        ]