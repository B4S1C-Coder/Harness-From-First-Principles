"""Sequential delegation with private tool histories and session-local handoffs."""

from collections import deque
from collections.abc import Callable, Iterable
from contextlib import closing
from typing import Any

from openai.types.chat import ChatCompletionMessage

from harness.compaction import tool_aware_compaction
from harness.exceptions import UnexpectedResponseError, ValueValidationError
from harness.llms import SyncTextLLMClient
from harness.log.investigator import InvestigationAgent, InvestigationConfig
from harness.log.log_backend import LogSource, SQLiteLogs
from harness.log.log_tools import (
    IncidentDigestTool,
    NearbyLogsTool,
    SearchLogsTool,
    TimelineTool,
    ScanSignaturesTool,
)
from harness.logger import ApplicationLogger
from harness.shortcuts.generic_scmt import SCMTTAgent, SCMTTConfig
from harness.token_estimator import TokenEstimator
from harness.tools import BaseTool, ExternalTool

from .config import CONTEXT_BUDGET, RCAConfig
from .prompts import Prompts


class _ReportHandler:
    def handle_message(self, message: ChatCompletionMessage) -> bool:
        if not message.content or not message.content.strip():
            raise UnexpectedResponseError("RCA agent", "Empty report.")
        return False


class ReportingAgent(_ReportHandler, SCMTTAgent[SCMTTConfig]):
    pass


class LogAgent(_ReportHandler, InvestigationAgent):
    pass


def run_turn(agent: SCMTTAgent, question: str) -> str:
    with agent.turn():
        agent.add_user_message(question)
        while agent.step():
            pass
        return str(agent.messages[-1]["content"])


def _clip(text: str, limit: int) -> str:
    encoded = text.encode()
    if len(encoded) <= limit:
        return text
    marker = b"[truncated]"[:limit]
    return encoded[: limit - len(marker)].decode(errors="ignore") + marker.decode()


class SpecialistTool(ExternalTool):
    parameters = {
        "type": "object",
        "properties": {"question": {"type": "string", "minLength": 1, "maxLength": 2000}},
        "required": ["question"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        name: str,
        description: str,
        investigate: Callable[[str], str],
        config: RCAConfig | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.investigate = investigate
        config = config or RCAConfig()
        self.cap = config.finding_bytes
        self.memory: deque[tuple[str, str]] = deque(maxlen=config.memory_size)

    def driver(self, args: dict[str, Any]) -> dict[str, str]:
        question = args["question"]
        if len(question.encode()) > 2000:
            raise ValueValidationError(
                "Use a focused specialist question of at most 2000 UTF-8 bytes."
            )
        # Keep room for evidence even when the specialist remembers many long handoffs.
        recent = []
        remaining = 2400
        for previous_question, answer in reversed(self.memory):
            entry = f"Question: {_clip(previous_question, 180)}\nFinding: {_clip(answer, 390)}\n"
            size = len(entry.encode())
            if size > remaining:
                break
            remaining -= size
            recent.append(entry)
        previous = "".join(reversed(recent))
        task = f"Prior handoffs (evidence):\n{previous}\nCurrent question:\n{question}"
        finding = _clip(self.investigate(task), self.cap)
        self.memory.append((question, finding))
        return {"finding": finding}


def build_log_agent(
    client: SyncTextLLMClient,
    logger: ApplicationLogger,
    db: SQLiteLogs,
    prompt: str,
    config: RCAConfig,
) -> LogAgent:
    return LogAgent(
        client=client,
        logger=logger,
        system_prompt=prompt,
        config=InvestigationConfig(
            backend=db,
            tools=[
                IncidentDigestTool(db),
                ScanSignaturesTool(db),
                TimelineTool(db),
                SearchLogsTool(db),
                NearbyLogsTool(db),
            ],
        ),
        context_budget=CONTEXT_BUDGET,
        token_estimator=TokenEstimator(encoding=None),
        max_tool_turns=config.log_max_tool_turns,
        recent_turns_to_keep=1,
        compaction=tool_aware_compaction,
    )


def build_master(
    master_client: SyncTextLLMClient,
    log_client: SyncTextLLMClient,
    research_client: SyncTextLLMClient,
    logger: ApplicationLogger,
    mcp_tools: Iterable[BaseTool],
    source: LogSource,
    prompts: Prompts,
    config: RCAConfig,
) -> ReportingAgent:
    remote_tools = tuple(mcp_tools)

    def agent(
        client: SyncTextLLMClient, prompt: str, tools: Iterable[BaseTool], turns: int
    ) -> ReportingAgent:
        return ReportingAgent(
            client=client,
            logger=logger,
            system_prompt=prompt,
            config=SCMTTConfig(tools),
            context_budget=CONTEXT_BUDGET,
            max_tool_turns=turns,
            recent_turns_to_keep=1,
            token_estimator=TokenEstimator(encoding=None),
            compaction=tool_aware_compaction,
        )

    def research(question: str) -> str:
        researcher = agent(
            research_client, prompts.research, remote_tools, config.research_max_tool_turns
        )
        return run_turn(researcher, question)

    def analyze(question: str) -> str:
        with closing(SQLiteLogs(source)) as db:
            investigator = build_log_agent(log_client, logger, db, prompts.logs, config)
            return run_turn(investigator, question)

    return agent(
        master_client,
        prompts.master,
        [
            SpecialistTool(
                "analyze_logs", "Investigate recent test-app Kafka logs.", analyze, config
            ),
            SpecialistTool(
                "research_mcp",
                "Research GitHub source, issues and Context7 documentation.",
                research,
                config,
            ),
        ],
        config.master_max_tool_turns,
    )
