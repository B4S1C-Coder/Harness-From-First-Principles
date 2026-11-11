from typing import override, Any

from openai.types.chat import ChatCompletionMessage
from harness.agents import SynchronousAgentBase
from harness.exceptions import UnexpectedResponseError, ToolExecutionError
from harness.tools import ToolRegistry, BaseTool

class HypothesisReviewerAgent(SynchronousAgentBase[None]):
    """ This is just a dummy sub agent to test the current harness with multiple agents. """
    @override
    def post_init(self, config: None) -> None:
        self.latest_response: str | None = None

    @override
    def handle_message(self, message: ChatCompletionMessage) -> bool:
        self.latest_response = message.content
        return False

    @override
    def handle_tool_call(self, message: ChatCompletionMessage) -> bool:
        raise UnexpectedResponseError(
            self.__class__.__name__, "This agent does not support tool calls."
        )

@ToolRegistry.register
class ReviewHypothesisTool(BaseTool):
    name = "review_hypothesis"

    description = (
        "Ask an independent technical reviewer to critically evaluate a root-cause hypothesis."
    )

    parameters = {
        "type": "object",
        "properties": {
            "hypothesis": {
                "type": "string",
                "description": "The hypothesis and supporting evidence to critically evaluate.",
            },
        },
        "required": ["hypothesis"],
        "additionalProperties": False,
    }

    def __init__(self, reviewer: HypothesisReviewerAgent) -> None:
        self.reviewer = reviewer

    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        self. reviewer.latest_response = None

        with self.reviewer.turn():
            self.reviewer.add_user_message(args["hypothesis"])
            should_continue = self.reviewer.step()

            if should_continue:
                raise ToolExecutionError(
                    "Reviewer unexpectedly requested continuation."
                )

        if self.reviewer.latest_response is None:
            raise ToolExecutionError("Reviewer returned no response.")

        return {
            "review": self.reviewer.latest_response,
        }