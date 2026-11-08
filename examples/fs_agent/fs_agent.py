import json
from openai.types.chat import (
    ChatCompletionMessage,
    ChatCompletionToolParam,
    ChatCompletionMessageFunctionToolCall,
)
from pathlib import Path
from typing import cast, override
from dataclasses import dataclass

from harness.agents import SynchronousAgentBase
from harness.exceptions import UnexpectedResponseError
from harness.shortcuts.fs_toolkit import virtual_fs_toolkit, virtual_readonly_fs_toolkit

@dataclass(frozen=True)
class FSAgentConfig:
    root: Path
    readonly: bool = False

class FileSystemAgent(SynchronousAgentBase[FSAgentConfig]):
    """ AI agent with basic file system capabilities. """

    @override
    def post_init(self, config: FSAgentConfig | None) -> None:
        if config is None:
            raise ValueError("FSAgentConfig object is required.")

        toolkit = (
            virtual_readonly_fs_toolkit
            if config.readonly
            else virtual_fs_toolkit
        )

        self.executor = toolkit(
            root=config.root,
            logger=self.logger,
        )

        self.tools = cast(
            list[ChatCompletionToolParam], list(self.executor.definitions().values())
        )

    @override
    def handle_message(self, message: ChatCompletionMessage) -> bool:
        """ Handle normal user message. """
        content = message.content
        
        if not content:
            raise UnexpectedResponseError(
                self.__class__.__qualname__, "Empty LLM response"
            )

        print(f"LLM Reply> {content}")

        # For normal messages end the turn
        return False

    @override
    def handle_tool_call(self, message: ChatCompletionMessage) -> bool:
        self.logger.debug("Executing tool calls...")

        for tool_call in message.tool_calls or []:
        
            if not isinstance(tool_call, ChatCompletionMessageFunctionToolCall):
                self.logger.warning("Unsupported tool call skipped")

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps({
                        "success": False,
                        "error": "Unsupported tool call type.",
                    }),
                })

                continue

            self.logger.debug(f"Executing tool call: {tool_call.function.name}")

            try:
                args = json.loads(tool_call.function.arguments)

            except json.JSONDecodeError as exc:
                result = json.dumps({
                    "success": False,
                    "error": f"Malformed tool arguments: {exc.msg}"
                })

            else:
                result = self.executor.execute(tool_call.function.name, args)

            self.messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })

        return True