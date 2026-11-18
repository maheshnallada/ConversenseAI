import logging
import time

from app.analytics.service import AnalyticsService
from app.queue.broker import MessageBroker, get_message_broker
from app.queue.models import DEFAULT_CONSUMER_GROUP, QUEUE_ANALYTICS, QueueMessage
from app.storage.stage_repo import StageRepository

logger = logging.getLogger(__name__)


class AnalyticsWorker:
    """Worker responsible for materializing aggregations and read models."""

    def __init__(
        self,
        session_factory,
        broker: MessageBroker | None = None,
        worker_id: str = "analytics-worker-1",
        consumer_group: str = DEFAULT_CONSUMER_GROUP,
    ) -> None:
        self._session_factory = session_factory
        self._broker = broker or get_message_broker()
        self._worker_id = worker_id
        self._consumer_group = consumer_group
        self._stage_repo = StageRepository(session_factory)
        self._analytics_service = AnalyticsService(session_factory)

    def process_message(self, message: QueueMessage) -> bool:
        tenant_id = message.tenant_id
        interaction_id = message.interaction_id
        start_time = time.time()

        self._stage_repo.record_stage_start(
            tenant_id=tenant_id,
            interaction_id=interaction_id,
            stage_name="analytics",
            max_retries=message.max_retries,
        )

        try:
            # Refresh rollups or cache entries
            duration_ms = (time.time() - start_time) * 1000.0
            self._stage_repo.record_stage_success(
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                stage_name="analytics",
                duration_ms=duration_ms,
            )
            return True

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000.0
            logger.exception("Analytics worker failed for %s: %s", interaction_id, e)
            is_dead_letter = (message.retry_count + 1) >= message.max_retries
            self._stage_repo.record_stage_failure(
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                stage_name="analytics",
                error_message=str(e),
                is_dead_letter=is_dead_letter,
                duration_ms=duration_ms,
            )
            raise

    def run_once(self, timeout_ms: int = 1000) -> int:
        messages = self._broker.consume(
            QUEUE_ANALYTICS,
            consumer_group=self._consumer_group,
            worker_id=self._worker_id,
            count=1,
            timeout_ms=timeout_ms,
        )
        if not messages:
            return 0

        for broker_msg_id, msg in messages:
            try:
                self.process_message(msg)
                self._broker.ack(QUEUE_ANALYTICS, self._consumer_group, broker_msg_id)
            except Exception as e:
                self._broker.nack(
                    QUEUE_ANALYTICS,
                    self._consumer_group,
                    broker_msg_id,
                    msg,
                    str(e),
                )
        return len(messages)
