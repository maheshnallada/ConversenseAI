from datetime import datetime, timezone
import pytest
from app.queue.broker import InMemoryBroker
from app.queue.models import QUEUE_GENERAL
from app.queue.outbox_publisher import OutboxPublisher
from app.storage.db import create_session_factory, init_db
from app.storage.orm import OutboxRow


@pytest.fixture
def session_factory(tmp_path):
    db_path = tmp_path / "test_outbox.db"
    sf = create_session_factory(f"sqlite:///{db_path}")
    init_db(sf)
    return sf


def test_outbox_publisher_sweeps_and_marks_published(session_factory):
    broker = InMemoryBroker()
    now = datetime.now(timezone.utc)

    # Insert unpublished outbox rows
    with session_factory() as session:
        session.add(
            OutboxRow(
                tenant_id="tenant-outbox",
                interaction_id="int-outbox-1",
                event_type="interaction.accepted",
                payload_json='{"key": "value1"}',
                created_at=now,
                published_at=None,
            )
        )
        session.add(
            OutboxRow(
                tenant_id="tenant-outbox",
                interaction_id="int-outbox-2",
                event_type="interaction.accepted",
                payload_json='{"key": "value2"}',
                created_at=now,
                published_at=None,
            )
        )
        session.commit()

    publisher = OutboxPublisher(session_factory, broker=broker)
    published = publisher.publish_pending()
    assert published == 2

    # Verify messages in broker queue
    stats = broker.get_queue_stats()
    assert stats["queues"][QUEUE_GENERAL] == 2

    # Second run should find 0 pending
    published_second = publisher.publish_pending()
    assert published_second == 0
