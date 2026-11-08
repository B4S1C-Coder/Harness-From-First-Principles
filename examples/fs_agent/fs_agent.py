import json
from openai.types.chat import (
    ChatCompletionMessage,
    ChatCompletionToolParam,
    ChatCompletionMessageFunctionToolCall,
)
from pathlib import Path
from typing import cast

from harness.agents import SynchronousAgentBase
from harness.exceptions import UnexpectedResponseError
from harness.shortcuts.fs_toolkit import virtual_fs_toolkit

class FileSystemAgent(SynchronousAgentBase):
    """ AI agent with basic file system capabilities. """

    def __init__(self, root: Path, *args, **kwargs) -> None:
        logger = kwargs.get("logger")

        if logger is None:
            raise ValueError("Logger must be provided as a keyword argument.")
        
        self.executor = virtual_fs_toolkit(root=root, logger=logger)
        
        super().__init__(
            *args,
            **kwargs,
            tools=cast(
                list[ChatCompletionToolParam],
                list(self.executor.definitions().values())
            ),
        )

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