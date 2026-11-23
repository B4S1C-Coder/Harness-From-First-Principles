from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv

from harness.llms import SyncTextLLMClient
from harness.logger import ApplicationLogger
from harness.mcp import MCPRuntime, load_mcp_config
from harness.shortcuts.generic_scmt import SCMTTAgent, SCMTTConfig
from harness.token_estimator import TokenEstimator

load_dotenv()

ROOT = Path(__file__).resolve().parent

def main() -> None:
    servers = load_mcp_config(ROOT / "servers.json")
    
    client = SyncTextLLMClient()
    prompt = (ROOT / "system.md").read_text(encoding="utf-8")
    
    with closing(ApplicationLogger(ROOT / "logs", console=True)) as logger:
        with MCPRuntime(servers, logger) as runtime:

            agent = SCMTTAgent(
                client=client,
                logger=logger,
                system_prompt=prompt,
                config=SCMTTConfig(tools=runtime.tools),
                token_estimator=TokenEstimator(encoding=None),
                max_tool_turns=3,
            )

            while True:
                try:
                    query = input("GitHub> ").strip()
                
                except EOFError:
                    return
                
                if query.lower() in {"exit", "quit"}:
                    return
                
                if query:
                    with agent.turn():
                        agent.add_user_message(query)
                        while agent.step():
                            pass


if __name__ == "__main__":
    main()
