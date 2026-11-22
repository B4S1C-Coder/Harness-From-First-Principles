"""Conversation-local scheduling for the experiment's investigation agent."""

import json
from collections.abc import Iterable, Callable
from dataclasses import dataclass
from typing import Any, cast, override

from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

from harness.exceptions import ConfigurationError
from harness.logger import ApplicationLogger
from harness.shortcuts.generic_scmt import SCMTTAgent, SCMTTConfig
from harness.tools import BaseTool, ToolExecutor
from . import log_preamble
from .log_backend import SQLiteLogs


@dataclass
class InvestigationConfig(SCMTTConfig):
    backend: SQLiteLogs


class InvestigationExecutor(ToolExecutor):
    def __init__(
        self, logger: ApplicationLogger, tools: Iterable[BaseTool], visible: Callable[[str], bool]
    ) -> None:
        super().__init__(logger, tools)
        self.visible = visible
        self.seen: set[tuple[str, str]] = set()

    @override
    def execute(self, name: str, args: dict[str, Any]) -> str:
        key = (name, json.dumps(args, sort_keys=True))
        if key in self.seen:
            return json.dumps(
                {"success": True, "data": {"see": "Identical call already made; result above"}}
            )
        self.seen.add(key)
        if (
            name in log_preamble.DEFAULT_CALLS
            and args == log_preamble.DEFAULT_CALLS[name]
            and self.visible(name)
        ):
            return json.dumps({"success": True, "data": {"see": f"Opening log evidence, {name}"}})
        return super().execute(name, args)


class InvestigationAgent(SCMTTAgent[InvestigationConfig]):
    @override
    def post_init(self, config: InvestigationConfig | None) -> None:
        if config is None:
            raise ConfigurationError("The investigation preamble requires a log backend.")
        self.backend = config.backend
        self.opening_message: ChatCompletionMessageParam | None = None
        self.complete_sections: set[str] = set()
        self.executor = InvestigationExecutor(self.logger, config.tools, self._visible)
        self.tools = cast(list[ChatCompletionToolParam], list(self.executor.definitions().values()))

    def _visible(self, name: str) -> bool:
        return name in self.complete_sections and any(
            message is self.opening_message for message in self.messages
        )

    @override
    def add_user_message(self, content: str) -> None:
        if content:
            self.executor.seen.clear()
            if len(self.messages) == 1:
                self._seed(content)
                # Opening evidence may be clipped. Only model-issued calls count for this run.
                self.executor.seen.clear()
        super().add_user_message(content)

    def _seed(self, question: str) -> None:
        estimator = self.token_estimator
        if estimator is None:
            raise ConfigurationError("The investigation preamble requires a token estimator.")

        def estimate(evidence: str) -> int:
            messages: list[ChatCompletionMessageParam] = [
                *self.messages,
                {"role": "user", "content": evidence},
                {"role": "user", "content": question},
            ]
            return estimator.next_request(messages, self.tools)

        pack = log_preamble.collect(self.backend, self.executor)
        content, complete, estimate_tokens = log_preamble.fit(
            pack, estimate, self.context_budget * self.compaction_threshold
        )
        self.opening_message = {"role": "user", "content": content}
        self.complete_sections = complete
        self.messages.append(self.opening_message)
        nearby = pack["nearby_logs"]
        self.logger.info(
            "Opening log evidence: bytes=%d estimated_request_tokens=%d pivots=%s "
            "omitted_error_families=%s pack_omitted_rows=%s",
            len(content.encode()),
            estimate_tokens,
            nearby.get("pivots", []),
            nearby.get("omitted_error_families"),
            {name: data.get("pack_omitted_rows", 0) for name, data in pack.items()},
        )
