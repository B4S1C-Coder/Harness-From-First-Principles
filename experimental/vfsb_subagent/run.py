from dotenv import load_dotenv
from pathlib import Path
from typing import Any
from harness.shortcuts.generic_scmt import SCMTTAgent, SCMTTConfig
from harness.builtin_tools.virtual_fs import ReadFileTool, ReadLinesTool, ListDirectoryTool
from harness.sandboxes import VirtualFileSystemSandbox
from harness.prompts import PromptStore
from harness.llms import SyncTextLLMClient
from harness.logger import ApplicationLogger
from harness.tools import ToolRegistry, BaseTool
from harness.exceptions import ToolExecutionError, UnexpectedResponseError
from harness.limits import VirtualFSReadLimits

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
PROMPT_ROOT = ROOT.parent / "examples" / "data"
MAIN_AGENT_MAX_STPES = 4

PromptStore.initialize(PROMPT_ROOT / "prompts.db")

readonly_workspace = VirtualFileSystemSandbox(
    root=ROOT / "data" / "workspace",
    can_read=True,
    can_write=False,
    can_execute=False
)

read_limits = VirtualFSReadLimits(
    max_bytes=4 * 1024,
    max_lines=30
)

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

    MAX_STEPS = 12

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
            raise UnexpectedResponseError(
                "Log analyzer did not produce a final response."
            )

        content = message.get("content")

        if not isinstance(content, str) or not content:
            raise UnexpectedResponseError(
                "Log analyzer returned an empty response."
            )

        return {
            "analysis": content,
        }

sub_agent = SCMTTAgent(
    client=SyncTextLLMClient(model="openai/gpt-oss-20b"),
    logger=logger,
    system_prompt=PromptStore.load_prompt("experimental.vfsb_subagent.sub.system"),
    compaction_threshold=0.8,
    recent_turns_to_keep=4,
    config=SCMTTConfig(tools=(
        ReadFileTool(readonly_workspace, limit=read_limits),
        ReadLinesTool(readonly_workspace, limit=read_limits),
        ListDirectoryTool(readonly_workspace),
    )),
)

main_agent = SCMTTAgent(
    client=SyncTextLLMClient(model="openai/gpt-oss-120b"),
    logger=logger,
    system_prompt=PromptStore.load_prompt("experimental.vfsb_subagent.main.system"),
    compaction_threshold=0.8,
    recent_turns_to_keep=4,
    config=SCMTTConfig(tools=(
        LogAgentTool(sub_agent),
    ))
)

try:
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
    logger.close()
    PromptStore.close()