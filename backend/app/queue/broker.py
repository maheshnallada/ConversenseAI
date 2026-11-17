import json
import logging
import os
import time
from typing import Any, Protocol, runtime_checkable

from app.queue.models import (
    DEFAULT_CONSUMER_GROUP,
    QUEUE_ANALYTICS,
    QUEUE_DLQ,
    QUEUE_EVALUATION,
    QUEUE_GENERAL,
    QueueMessage,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class MessageBroker(Protocol):
    def publish(self, queue: str, message: QueueMessage) -> str:
        ...

    def consume(
        self,
        queue: str,
        consumer_group: str = DEFAULT_CONSUMER_GROUP,
        worker_id: str = "worker-1",
        count: int = 1,
        timeout_ms: int = 2000,
    ) -> list[tuple[str, QueueMessage]]:
        """Returns list of (broker_msg_id, QueueMessage)"""
        ...

    def ack(self, queue: str, consumer_group: str, broker_msg_id: str) -> None:
        ...

    def nack(
        self,
        queue: str,
        consumer_group: str,
        broker_msg_id: str,
        message: QueueMessage,
        error: str,
    ) -> None:
        ...

    def dead_letter(
        self,
        queue: str,
        consumer_group: str,
        broker_msg_id: str,
        message: QueueMessage,
        reason: str,
    ) -> None:
        ...

    def get_queue_stats(self) -> dict[str, Any]:
        ...


class InMemoryBroker:
    def __init__(self) -> None:
        self._queues: dict[str, list[tuple[str, QueueMessage]]] = {
            QUEUE_GENERAL: [],
            QUEUE_EVALUATION: [],
            QUEUE_ANALYTICS: [],
            QUEUE_DLQ: [],
        }
        self._pending: dict[str, dict[str, tuple[str, QueueMessage]]] = {}
        self._counter = 0

    def publish(self, queue: str, message: QueueMessage) -> str:
        self._counter += 1
        broker_id = f"mem-{self._counter}"
        if queue not in self._queues:
            self._queues[queue] = []
        self._queues[queue].append((broker_id, message))
        return broker_id

    def consume(
        self,
        queue: str,
        consumer_group: str = DEFAULT_CONSUMER_GROUP,
        worker_id: str = "worker-1",
        count: int = 1,
        timeout_ms: int = 2000,
    ) -> list[tuple[str, QueueMessage]]:
        items = []
        q = self._queues.get(queue, [])
        for _ in range(min(count, len(q))):
            broker_id, msg = q.pop(0)
            group_key = f"{queue}:{consumer_group}"
            if group_key not in self._pending:
                self._pending[group_key] = {}
            self._pending[group_key][broker_id] = (broker_id, msg)
            items.append((broker_id, msg))
        return items

    def ack(self, queue: str, consumer_group: str, broker_msg_id: str) -> None:
        group_key = f"{queue}:{consumer_group}"
        if group_key in self._pending:
            self._pending[group_key].pop(broker_msg_id, None)

    def nack(
        self,
        queue: str,
        consumer_group: str,
        broker_msg_id: str,
        message: QueueMessage,
        error: str,
    ) -> None:
        self.ack(queue, consumer_group, broker_msg_id)
        message.retry_count += 1
        message.error_reason = error
        if message.retry_count >= message.max_retries:
            self.publish(QUEUE_DLQ, message)
        else:
            self.publish(queue, message)

    def dead_letter(
        self,
        queue: str,
        consumer_group: str,
        broker_msg_id: str,
        message: QueueMessage,
        reason: str,
    ) -> None:
        self.ack(queue, consumer_group, broker_msg_id)
        message.error_reason = reason
        self.publish(QUEUE_DLQ, message)

    def get_queue_stats(self) -> dict[str, Any]:
        return {
            "type": "in_memory",
            "queues": {q: len(items) for q, items in self._queues.items()},
        }


class RedisStreamsBroker:
    def __init__(self, redis_client) -> None:
        self._redis = redis_client
        self._ensured_groups: set[str] = set()

    def _ensure_group(self, queue: str, group: str) -> None:
        group_key = f"{queue}:{group}"
        if group_key in self._ensured_groups:
            return
        try:
            self._redis.xgroup_create(queue, group, id="0", mkstream=True)
        except Exception as e:
            # Group already exists is expected
            if "BUSYGROUP" not in str(e):
                logger.warning("Error creating consumer group %s on %s: %s", group, queue, e)
        self._ensured_groups.add(group_key)

    def publish(self, queue: str, message: QueueMessage) -> str:
        payload = {"data": json.dumps(message.to_dict())}
        broker_id = self._redis.xadd(queue, payload)
        return str(broker_id)

    def consume(
        self,
        queue: str,
        consumer_group: str = DEFAULT_CONSUMER_GROUP,
        worker_id: str = "worker-1",
        count: int = 1,
        timeout_ms: int = 2000,
    ) -> list[tuple[str, QueueMessage]]:
        self._ensure_group(queue, consumer_group)
        try:
            entries = self._redis.xreadgroup(
                consumer_group,
                worker_id,
                {queue: ">"},
                count=count,
                block=timeout_ms,
            )
        except Exception as e:
            logger.error("Error reading stream %s group %s: %s", queue, consumer_group, e)
            return []

        results: list[tuple[str, QueueMessage]] = []
        if not entries:
            return results

        for stream_name, msg_list in entries:
            for b_id, fields in msg_list:
                str_id = b_id.decode("utf-8") if isinstance(b_id, bytes) else str(b_id)
                raw_data = fields.get(b"data") or fields.get("data")
                if isinstance(raw_data, bytes):
                    raw_data = raw_data.decode("utf-8")
                try:
                    data = json.loads(raw_data)
                    msg = QueueMessage.from_dict(data)
                    results.append((str_id, msg))
                except Exception as ex:
                    logger.error("Failed to parse queue message %s: %s", str_id, ex)
                    # Automatically acknowledge malformed messages to prevent deadlocks
                    self.ack(queue, consumer_group, str_id)

        return results

    def ack(self, queue: str, consumer_group: str, broker_msg_id: str) -> None:
        try:
            self._redis.xack(queue, consumer_group, broker_msg_id)
        except Exception as e:
            logger.error("Failed to ack message %s on %s: %s", broker_msg_id, queue, e)

    def nack(
        self,
        queue: str,
        consumer_group: str,
        broker_msg_id: str,
        message: QueueMessage,
        error: str,
    ) -> None:
        self.ack(queue, consumer_group, broker_msg_id)
        message.retry_count += 1
        message.error_reason = error
        if message.retry_count >= message.max_retries:
            self.dead_letter(queue, consumer_group, broker_msg_id, message, error)
        else:
            self.publish(queue, message)

    def dead_letter(
        self,
        queue: str,
        consumer_group: str,
        broker_msg_id: str,
        message: QueueMessage,
        reason: str,
    ) -> None:
        self.ack(queue, consumer_group, broker_msg_id)
        message.error_reason = reason
        self.publish(QUEUE_DLQ, message)

    def get_queue_stats(self) -> dict[str, Any]:
        stats: dict[str, Any] = {"type": "redis_streams", "queues": {}}
        for q in [QUEUE_GENERAL, QUEUE_EVALUATION, QUEUE_ANALYTICS, QUEUE_DLQ]:
            try:
                stats["queues"][q] = self._redis.xlen(q)
            except Exception:
                stats["queues"][q] = 0
        return stats


_GLOBAL_BROKER: MessageBroker | None = None


def get_message_broker(redis_url: str | None = None) -> MessageBroker:
    global _GLOBAL_BROKER
    if _GLOBAL_BROKER is not None:
        return _GLOBAL_BROKER

    url = redis_url or os.getenv("REDIS_URL")
    if url:
        try:
            import redis
            client = redis.Redis.from_url(url)
            client.ping()
            logger.info("Connected to Redis Streams broker at %s", url)
            _GLOBAL_BROKER = RedisStreamsBroker(client)
            return _GLOBAL_BROKER
        except Exception as e:
            logger.warning("Could not connect to Redis at %s (%s). Falling back to InMemoryBroker.", url, e)

    _GLOBAL_BROKER = InMemoryBroker()
    return _GLOBAL_BROKER


def set_message_broker(broker: MessageBroker | None) -> None:
    global _GLOBAL_BROKER
    _GLOBAL_BROKER = broker
