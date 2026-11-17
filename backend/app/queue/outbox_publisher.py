import json
import logging
import time
from datetime import datetime, timezone
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.queue.broker import MessageBroker, get_message_broker
from app.queue.models import QUEUE_GENERAL, QueueMessage
from app.storage.orm import OutboxRow

logger = logging.getLogger(__name__)


class OutboxPublisher:
    def __init__(self, session_factory, broker: MessageBroker | None = None) -> None:
        self._session_factory = session_factory
        self._broker = broker or get_message_broker()

    def publish_pending(self, batch_size: int = 50) -> int:
        published_count = 0
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            rows = session.execute(
                select(OutboxRow)
                .where(OutboxRow.published_at.is_(None))
                .order_by(OutboxRow.created_at)
                .limit(batch_size)
            ).scalars().all()

            for row in rows:
                try:
                    payload_dict = {}
                    if row.payload_json:
                        try:
                            payload_dict = json.loads(row.payload_json)
                        except Exception:
                            pass

                    msg = QueueMessage(
                        tenant_id=row.tenant_id,
                        interaction_id=row.interaction_id,
                        stage="general",
                        payload={"event_type": row.event_type, "envelope": payload_dict},
                    )
                    self._broker.publish(QUEUE_GENERAL, msg)
                    row.published_at = now
                    published_count += 1
                except Exception as e:
                    logger.error("Failed to publish outbox event %s: %s", row.id, e)

            if published_count > 0:
                session.commit()

        return published_count

    def run_loop(self, poll_interval_s: float = 0.5, stop_event: threading.Event | None = None) -> None:
        logger.info("Starting outbox publisher loop...")
        while stop_event is None or not stop_event.is_set():
            try:
                count = self.publish_pending()
                if count == 0:
                    time.sleep(poll_interval_s)
            except Exception as e:
                logger.error("Outbox publisher loop error: %s", e)
                time.sleep(poll_interval_s)
