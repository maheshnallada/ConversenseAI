import pytest
from app.queue.broker import InMemoryBroker
from app.queue.models import (
    DEFAULT_CONSUMER_GROUP,
    QUEUE_DLQ,
    QUEUE_EVALUATION,
    QUEUE_GENERAL,
    QueueMessage,
)


def test_in_memory_broker_publish_and_consume():
    broker = InMemoryBroker()
    msg = QueueMessage(
        tenant_id="tenant-1",
        interaction_id="int-1",
        stage="general",
        payload={"foo": "bar"},
    )
    broker_id = broker.publish(QUEUE_GENERAL, msg)
    assert broker_id.startswith("mem-")

    stats = broker.get_queue_stats()
    assert stats["queues"][QUEUE_GENERAL] == 1

    messages = broker.consume(QUEUE_GENERAL, count=1)
    assert len(messages) == 1
    b_id, consumed_msg = messages[0]
    assert b_id == broker_id
    assert consumed_msg.interaction_id == "int-1"
    assert consumed_msg.payload == {"foo": "bar"}

    # Pending exists until acked
    broker.ack(QUEUE_GENERAL, DEFAULT_CONSUMER_GROUP, b_id)
    assert len(broker._pending[f"{QUEUE_GENERAL}:{DEFAULT_CONSUMER_GROUP}"]) == 0


def test_in_memory_broker_nack_retries_and_dlq():
    broker = InMemoryBroker()
    msg = QueueMessage(
        tenant_id="tenant-1",
        interaction_id="int-fail",
        stage="evaluation",
        max_retries=2,
    )
    b_id = broker.publish(QUEUE_EVALUATION, msg)

    # First attempt fails -> retried back to queue
    consumed = broker.consume(QUEUE_EVALUATION, count=1)
    b_id, m = consumed[0]
    broker.nack(QUEUE_EVALUATION, DEFAULT_CONSUMER_GROUP, b_id, m, "LLM timeout")

    assert m.retry_count == 1
    stats = broker.get_queue_stats()
    assert stats["queues"][QUEUE_EVALUATION] == 1
    assert stats["queues"][QUEUE_DLQ] == 0

    # Second attempt fails -> exceeds max_retries -> goes to DLQ
    consumed = broker.consume(QUEUE_EVALUATION, count=1)
    b_id, m = consumed[0]
    broker.nack(QUEUE_EVALUATION, DEFAULT_CONSUMER_GROUP, b_id, m, "LLM rate limit")

    assert m.retry_count == 2
    stats = broker.get_queue_stats()
    assert stats["queues"][QUEUE_EVALUATION] == 0
    assert stats["queues"][QUEUE_DLQ] == 1
