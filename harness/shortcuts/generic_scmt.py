import json
from typing import override, cast
from collections.abc import Iterable
from dataclasses import dataclass
from openai.types.chat import (
    ChatCompletionMessage,
    ChatCompletionToolParam,
    ChatCompletionMessageFunctionToolCall,
)

from ..agents import SynchronousAgentBase
from ..tools import ToolExecutor, BaseTool
from ..exceptions import UnexpectedResponseError


@dataclass
class SCMTTConfig:
    tools: Iterable[BaseTool]


class SCMTTAgent[ConfigT: SCMTTConfig](SynchronousAgentBase[ConfigT]):
    """
    # Single Conversation, Multiple Tool Turns (SCMTT) Agent
    A lightweight implementation of SynchronousAgentBase, based on observed usage patterns.
    A normal llm message ends the turn while a tool call continues it (till specified limit).
    """

    @override
    def post_init(self, config: ConfigT | None) -> None:
        tools = config.tools if config is not None else []

        self.executor = ToolExecutor(
            logger=self.logger,
            tools=tools,
        )

        self.tools = cast(list[ChatCompletionToolParam], list(self.executor.definitions().values()))

    @override
    def handle_message(self, message: ChatCompletionMessage) -> bool:
        """Handle normal user message."""
        content = message.content

        if not content:
            raise UnexpectedResponseError(self.__class__.__qualname__, "Empty LLM response")

        print(f"LLM Reply> {content}")

        # For normal messages end the turn
        return False

    @override
    def handle_tool_call(self, message: ChatCompletionMessage) -> bool:
        self.logger.debug("Executing tool calls...")

        for tool_call in message.tool_calls or []:
            if not isinstance(tool_call, ChatCompletionMessageFunctionToolCall):
                self.logger.warning("Unsupported tool call skipped")

                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(
                            {
                                "success": False,
                                "error": "Unsupported tool call type.",
                            }
                        ),
                    }
                )

                continue

            self.logger.debug(
                "Tool request: %s",
                json.dumps(
                    {
                        "call_id": tool_call.id,
                        "tool": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                    ensure_ascii=False,
                ),
            )

            try:
                args = json.loads(tool_call.function.arguments)

            except json.JSONDecodeError as exc:
                result = json.dumps(
                    {"success": False, "error": f"Malformed tool arguments: {exc.msg}"}
                )

            else:
                result = self.executor.execute(tool_call.function.name, args)

            response = json.loads(result)
            data = response.get("data")
            details = {
                "call_id": tool_call.id,
                "tool": tool_call.function.name,
                "success": response.get("success"),
                "error": response.get("error"),
                "result_bytes": len(result.encode("utf-8")),
            }
            if isinstance(data, dict):
                if data.get("error"):
                    details.update(success=False, error=data["error"])
                rows, columns = data.get("rows"), data.get("columns", [])
                if isinstance(rows, list):
                    details["row_count"] = len(rows)
                    details["truncated"] = data.get("truncated", False)
                    if "filename" in columns and "line" in columns:
                        file_index, line_index = columns.index("filename"), columns.index("line")
                        details["source_references"] = [
                            {"filename": row[file_index], "line": row[line_index]}
                            for row in rows
                            if isinstance(row, list) and len(row) > max(file_index, line_index)
                        ]
                if "query" in data:
                    details["query"] = data["query"]
            self.logger.debug("Tool result: %s", json.dumps(details, ensure_ascii=False))

            self.messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

        return True
