from dotenv import load_dotenv
from pathlib import Path
from typing import Any
from harness.shortcuts.generic_scmt import SCMTTAgent, SCMTTConfig
from harness.compaction import tool_aware_compaction
from experimental.vfsb_subagent.log_backend import SQLiteLogs
from experimental.vfsb_subagent.query_helper import QueryHelper
from experimental.vfsb_subagent.log_tools import (
    LogOverviewTool,
    SearchLogsTool,
    NearbyLogsTool,
    AdvancedLogAnalysisTool,
)
from harness.prompts import PromptStore
from harness.llms import SyncTextLLMClient
from harness.logger import ApplicationLogger
from harness.tools import ToolRegistry, BaseTool
from harness.exceptions import ToolExecutionError, UnexpectedResponseError

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
PROMPT_ROOT = ROOT.parent / "examples" / "data"
MAIN_AGENT_MAX_STPES = 4

PromptStore.initialize(PROMPT_ROOT / "prompts.db")

logger = ApplicationLogger(ROOT / "data", console=True)


@ToolRegistry.register
class LogAgentTool(BaseTool):
    name = "analyze_logs"

    description = (
        "Investigate application logs to identify errors, anomalies, "
        "failure sequences, and possible root causes. "
        "The analyzer can inspect log files, correlate events across files, "
        "and return an evidence-based investigation report. "
        "Use this when diagnosing incidents or when log evidence "
        "is needed to verify a hypothesis."
    )

    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": (
                    "A clear investigation request describing what the "
                    "analyzer should look for. Include known symptoms, "
                    "relevant timestamps, suspected causes, or specific "
                    "questions when available."
                ),
            },
        },
        "required": ["task"],
        "additionalProperties": False,
    }

    MAX_TOOL_TURNS = 6
    MAX_STEPS = MAX_TOOL_TURNS + 1  # Reserve one tools-disabled final summary.

    def __init__(self, agent: SCMTTAgent) -> None:
        self.agent = agent

    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        task = args["task"]

        with self.agent.turn():
            self.agent.add_user_message(task)

            for _ in range(self.MAX_STEPS):
                if not self.agent.step():
                    break
            else:
                raise ToolExecutionError(
                    "Log analyzer exceeded its step limit without completing the investigation."
                )

        message = self.agent.messages[-1]

        if message["role"] != "assistant":
            raise UnexpectedResponseError("Log analyzer did not produce a final response.")

        content = message.get("content")

        if not isinstance(content, str) or not content:
            raise UnexpectedResponseError("Log analyzer returned an empty response.")

        return {
            "analysis": content,
        }


backend = SQLiteLogs(ROOT / "data" / "workspace")
try:
    query_helper = QueryHelper(backend, SyncTextLLMClient(model="openai/gpt-oss-20b"))

    sub_agent = SCMTTAgent(
        client=SyncTextLLMClient(model="openai/gpt-oss-20b"),
        logger=logger,
        system_prompt=PromptStore.load_prompt("experimental.vfsb_subagent.sub.system"),
        context_budget=8_000,
        enable_context_check=False,  # Temporarily bypass the byte-based estimate.
        max_tool_turns=LogAgentTool.MAX_TOOL_TURNS,
        compaction_threshold=0.75,
        recent_turns_to_keep=1,
        compaction=tool_aware_compaction,
        config=SCMTTConfig(
            tools=(
                LogOverviewTool(backend),
                SearchLogsTool(backend),
                NearbyLogsTool(backend),
                AdvancedLogAnalysisTool(query_helper),
            )
        ),
    )

    main_agent = SCMTTAgent(
        client=SyncTextLLMClient(model="openai/gpt-oss-120b"),
        logger=logger,
        system_prompt=PromptStore.load_prompt("experimental.vfsb_subagent.main.system"),
        context_budget=8_000,
        enable_context_check=False,
        compaction_threshold=0.75,
        recent_turns_to_keep=1,
        compaction=tool_aware_compaction,
        config=SCMTTConfig(tools=(LogAgentTool(sub_agent),)),
    )

    while True:
        q = input("User> ").strip()

        if q.lower() in ("exit", "quit"):
            break

        if not q:
            continue

        with main_agent.turn():
            main_agent.add_user_message(q)

            for _ in range(MAIN_AGENT_MAX_STPES):
                if not main_agent.step():
                    break
finally:
    backend.close()
    logger.close()
    PromptStore.close()
