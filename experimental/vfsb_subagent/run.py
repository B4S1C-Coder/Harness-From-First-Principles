from pathlib import Path

from dotenv import load_dotenv

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

ROOT = Path(__file__).resolve().parent.parent
PROMPT_ROOT = ROOT.parent / "examples" / "data"
MAIN_AGENT_MAX_TOOL_TURNS = 12
MAIN_AGENT_MAX_STEPS = MAIN_AGENT_MAX_TOOL_TURNS + 1


def build_agent(
    backend: SQLiteLogs,
    logger: ApplicationLogger,
    investigation_client: SyncTextLLMClient,
    query_client: SyncTextLLMClient,
    system_prompt: str,
) -> SCMTTAgent:
    """The investigator owns retrieval and RCA; the helper only generates queries."""
    query_helper = QueryHelper(backend, query_client)
    return SCMTTAgent(
        client=investigation_client,
        logger=logger,
        system_prompt=system_prompt,
        context_budget=8_000,
        enable_context_check=False,
        max_tool_turns=MAIN_AGENT_MAX_TOOL_TURNS,
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


def main() -> None:
    load_dotenv()
    PromptStore.initialize(PROMPT_ROOT / "prompts.db")
    logger = ApplicationLogger(ROOT / "data", console=True)
    backend = None
    try:
        backend = SQLiteLogs(ROOT / "data" / "workspace")
        agent = build_agent(
            backend,
            logger,
            SyncTextLLMClient(model="openai/gpt-oss-120b"),
            SyncTextLLMClient(model="openai/gpt-oss-20b"),
            PromptStore.load_prompt("experimental.vfsb_subagent.main.system"),
        )
        while True:
            query = input("User> ").strip()
            if query.lower() in ("exit", "quit"):
                break
            if not query:
                continue
            with agent.turn():
                agent.add_user_message(query)
                for _ in range(MAIN_AGENT_MAX_STEPS):
                    if not agent.step():
                        break
    finally:
        if backend is not None:
            backend.close()
        logger.close()
        PromptStore.close()


if __name__ == "__main__":
    main()
