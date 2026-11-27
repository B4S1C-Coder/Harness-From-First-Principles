from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv

from harness.exceptions import ApplicationException
from harness.llms import SyncTextLLMClient, TextOnlyRetryClient
from harness.logger import ApplicationLogger
from harness.mcp import MCPRuntime, load_mcp_config

from .agents import build_master, run_turn
from .config import RCAConfig
from .prompts import load_prompts, prompt_store

ROOT = Path(__file__).resolve().parent


def main() -> None:
    load_dotenv()
    config = RCAConfig.from_env()
    with prompt_store():
        prompts = load_prompts()
    from .kafka import KafkaLogSource

    source = KafkaLogSource(config.brokers, config.topic, config.offsets_per_partition)
    with closing(ApplicationLogger(ROOT / "logs", console=True)) as logger:
        with MCPRuntime(load_mcp_config(ROOT / "servers.json"), logger) as runtime:
            master = build_master(
                TextOnlyRetryClient(SyncTextLLMClient(model=config.master_model)),
                TextOnlyRetryClient(SyncTextLLMClient(model=config.log_model)),
                TextOnlyRetryClient(SyncTextLLMClient(model=config.research_model)),
                logger,
                runtime.tools,
                source,
                prompts,
                config,
            )
            while True:
                try:
                    question = input("RCA> ").strip()
                except EOFError:
                    return
                if question.lower() in {"quit", "exit"}:
                    return
                if question:
                    try:
                        logger.info("%s", run_turn(master, question))
                    except ApplicationException as exc:
                        logger.warning("Turn failed: %s", exc)
                        master.reset()


if __name__ == "__main__":
    main()
