"""Finite Kafka snapshots for harness.log.SQLiteLogs."""

from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from time import monotonic
from uuid import uuid4

from confluent_kafka import Consumer, KafkaError, KafkaException, TopicPartition

from harness.exceptions import TimeoutError, ToolExecutionError


from .config import RCAConfig


@dataclass(frozen=True)
class KafkaLogSource:
    brokers: str = RCAConfig.brokers
    topic: str = RCAConfig.topic
    offsets_per_partition: int = RCAConfig.offsets_per_partition

    def lines(self) -> Iterator[tuple[str, str]]:
        try:
            with closing(
                Consumer(
                    {
                        "bootstrap.servers": self.brokers,
                        "group.id": f"rca-{uuid4().hex}",
                        "enable.auto.commit": False,
                        "allow.auto.create.topics": False,
                        "enable.partition.eof": True,
                        "auto.offset.reset": "error",
                    }
                )
            ) as consumer:
                yield from self._snapshot(consumer)
        except KafkaException as exc:
            raise ToolExecutionError(f"Kafka snapshot failed for {self.topic}: {exc}") from exc

    def _snapshot(self, consumer: Consumer) -> Iterator[tuple[str, str]]:
        meta = consumer.list_topics(self.topic, timeout=5).topics.get(self.topic)
        if meta is None or meta.error:
            raise ToolExecutionError(f"Kafka topic {self.topic} unavailable: {meta and meta.error}")

        starts, ends = {}, {}
        for partition in sorted(meta.partitions):
            tp = TopicPartition(self.topic, partition)
            low, high = consumer.get_watermark_offsets(tp, timeout=5)
            if low < high:
                starts[partition] = max(low, high - self.offsets_per_partition)
                ends[partition] = high
        if not ends:
            return
        consumer.assign([TopicPartition(self.topic, p, start) for p, start in starts.items()])
        deadline = monotonic() + 20
        while ends:
            if monotonic() >= deadline:
                raise TimeoutError(f"Kafka snapshot of {self.topic}")
            record = consumer.poll(0.5)
            if record is None:
                continue
            partition, offset = record.partition(), record.offset()
            error = record.error()
            if error and error.code() != KafkaError._PARTITION_EOF:
                raise ToolExecutionError(f"Kafka read failed: {error}")
            if partition not in ends:
                continue
            end = ends[partition]
            if not error and offset < end and record.value() is not None:
                source = f"{self.topic}[{partition}]@{starts[partition]}"
                yield source, record.value().decode("utf-8", errors="replace")
            if offset >= end or (not error and offset + 1 == end):
                del ends[partition]
                consumer.pause([TopicPartition(self.topic, partition)])
