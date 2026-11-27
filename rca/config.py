from dataclasses import dataclass, fields

from harness.exceptions import ConfigurationError
from harness.helpers import load_env

CONTEXT_BUDGET = 8000


@dataclass(frozen=True)
class RCAConfig:
    master_model: str = "openai/gpt-oss-120b"
    log_model: str = "openai/gpt-oss-120b"
    research_model: str = "openai/gpt-oss-20b"
    master_max_tool_turns: int = 6
    log_max_tool_turns: int = 6
    research_max_tool_turns: int = 6
    finding_bytes: int = 1200
    memory_size: int = 4
    brokers: str = "localhost:9092"
    topic: str = "app-logs"
    offsets_per_partition: int = 1000

    def __post_init__(self) -> None:
        if not 1 <= self.finding_bytes <= 1800:
            raise ConfigurationError("RCA_FINDING_BYTES must be between 1 and 1800.")
        if self.offsets_per_partition < 1:
            raise ConfigurationError("KAFKA_OFFSETS_PER_PARTITION must be positive.")
        if (
            min(
                self.master_max_tool_turns,
                self.log_max_tool_turns,
                self.research_max_tool_turns,
                self.memory_size,
            )
            < 0
        ):
            raise ConfigurationError("RCA tool-turn and memory limits must be nonnegative.")

    @classmethod
    def from_env(cls) -> "RCAConfig":
        kafka = {
            "brokers": "KAFKA_BOOTSTRAP_SERVERS",
            "topic": "KAFKA_LOG_TOPIC",
            "offsets_per_partition": "KAFKA_OFFSETS_PER_PARTITION",
        }
        values = {}
        for field in fields(cls):
            name = kafka.get(field.name, f"RCA_{field.name.upper()}")
            values[field.name] = load_env(name, cast=type(field.default), default=field.default)
        return cls(**values)
