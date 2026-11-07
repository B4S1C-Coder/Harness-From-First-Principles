import json
from openai.types.chat import (
    ChatCompletionMessage,
    ChatCompletionMessageFunctionToolCall
)
from harness.agents import SynchronousAgentBase
from harness.exceptions import UnexpectedResponseError
from harness.tools import ToolRegistry

class BasicAgent(SynchronousAgentBase):
    def handle_message(self, message: ChatCompletionMessage) -> bool:
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
                continue

            self.logger.debug(f"Executing tool call: {tool_call.function.name}")

            result = ToolRegistry.execute(
                tool_call.function.name, json.loads(tool_call.function.arguments)
            )

            self.messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result),
            })

        # For tool calls continue the turn (LLM gets multiple chances to run tools)
        return True

