import os
from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv

from harness.exceptions import ApplicationException
from harness.llms import SyncTextLLMClient, TextOnlyRetryClient
from harness.logger import ApplicationLogger
from harness.mcp import MCPRuntime, load_mcp_config

from .agents import build_master, run_turn
from .kafka import KafkaLogSource

ROOT = Path(__file__).resolve().parent


def main() -> None:
    load_dotenv()
    source = KafkaLogSource(
        os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        os.getenv("KAFKA_LOG_TOPIC", "app-logs"),
    )
    with closing(ApplicationLogger(ROOT / "logs", console=True)) as logger:
        with MCPRuntime(load_mcp_config(ROOT / "servers.json"), logger) as runtime:
            master = build_master(
                TextOnlyRetryClient(SyncTextLLMClient(model="openai/gpt-oss-120b")),
                TextOnlyRetryClient(SyncTextLLMClient(model="openai/gpt-oss-20b")),
                logger,
                runtime.tools,
                source,
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
