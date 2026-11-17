import asyncio
import logging
import time
from typing import Any

from app.ingestion.service import IngestionService
from app.observability.service import ObservabilityService
from app.queue.broker import MessageBroker, get_message_broker
from app.queue.models import (
    DEFAULT_CONSUMER_GROUP,
    QUEUE_ANALYTICS,
    QUEUE_EVALUATION,
    QUEUE_GENERAL,
    QueueMessage,
)
from app.reconstruction.reconstructor import TimelineReconstructor
from app.storage.observability_repo import ObservabilityRepository
from app.storage.stage_repo import StageRepository
from app.storage.timeline_repo import TimelineRepository
from app.storage.transcript_repo import TranscriptRepository

logger = logging.getLogger(__name__)


class GeneralWorker:
    """Worker responsible for timeline reconstruction and deterministic observability metrics."""

    def __init__(
        self,
        session_factory,
        broker: MessageBroker | None = None,
        worker_id: str = "general-worker-1",
        consumer_group: str = DEFAULT_CONSUMER_GROUP,
    ) -> None:
        self._session_factory = session_factory
        self._broker = broker or get_message_broker()
        self._worker_id = worker_id
        self._consumer_group = consumer_group

        self._ingestion_service = IngestionService(session_factory)
        self._transcript_repo = TranscriptRepository(session_factory)
        self._timeline_reconstructor = TimelineReconstructor()
        self._timeline_repo = TimelineRepository(session_factory)
        self._observability_service = ObservabilityService(session_factory)
        self._observability_repo = ObservabilityRepository(session_factory)
        self._stage_repo = StageRepository(session_factory)

    async def process_message_async(self, message: QueueMessage) -> bool:
        tenant_id = message.tenant_id
        interaction_id = message.interaction_id
        start_time = time.time()

        await asyncio.to_thread(
            self._stage_repo.record_stage_start,
            tenant_id=tenant_id,
            interaction_id=interaction_id,
            stage_name="general",
            max_retries=message.max_retries,
        )

        try:
            envelope = await asyncio.to_thread(self._ingestion_service.get, tenant_id, interaction_id)
            if envelope is None:
                raise ValueError(f"Interaction {interaction_id} not found for tenant {tenant_id}")

            turns = await asyncio.to_thread(self._transcript_repo.get_turns, tenant_id, interaction_id)

            # 1. Timeline reconstruction (idempotent)
            existing_timeline = await asyncio.to_thread(self._timeline_repo.get_timeline, tenant_id, interaction_id)
            if existing_timeline is None:
                timeline = await asyncio.to_thread(
                    self._timeline_reconstructor.reconstruct,
                    tenant_id=tenant_id,
                    interaction_id=interaction_id,
                    turns=turns,
                    call_metadata=(envelope.domain_data or {}).get("meta"),
                    events=envelope.events,
                )
                await asyncio.to_thread(self._timeline_repo.save_timeline, timeline)

            # 2. Observability metrics calculation (idempotent)
            existing_metrics = await asyncio.to_thread(self._observability_repo.get_metrics, tenant_id, interaction_id)
            if existing_metrics is None:
                await asyncio.to_thread(
                    self._observability_service.calculate_interaction,
                    tenant_id=tenant_id,
                    interaction_id=interaction_id,
                    turns=turns,
                    events=envelope.events,
                    call_data=envelope.domain_data,
                )

            duration_ms = (time.time() - start_time) * 1000.0
            await asyncio.to_thread(
                self._stage_repo.record_stage_success,
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                stage_name="general",
                duration_ms=duration_ms,
            )

            # 3. Dispatch to evaluation and analytics streams
            eval_msg = QueueMessage(
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                stage="evaluation",
                correlation_id=message.correlation_id,
            )
            await asyncio.to_thread(self._broker.publish, QUEUE_EVALUATION, eval_msg)

            analytics_msg = QueueMessage(
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                stage="analytics",
                correlation_id=message.correlation_id,
            )
            await asyncio.to_thread(self._broker.publish, QUEUE_ANALYTICS, analytics_msg)

            return True

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000.0
            logger.exception("General worker failed for %s: %s", interaction_id, e)
            await asyncio.to_thread(
                self._stage_repo.record_stage_failure,
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                stage_name="general",
                error_message=str(e),
                duration_ms=duration_ms,
            )
            raise

    def process_message(self, message: QueueMessage) -> bool:
        """Synchronous wrapper for process_message_async."""
        return asyncio.run(self.process_message_async(message))

    async def run_batch_async(self, count: int = 5, timeout_ms: int = 1000) -> int:
        """Pulls a batch of messages and executes reconstruction/metrics concurrently."""
        messages = await asyncio.to_thread(
            self._broker.consume,
            QUEUE_GENERAL,
            consumer_group=self._consumer_group,
            worker_id=self._worker_id,
            count=count,
            timeout_ms=timeout_ms,
        )
        if not messages:
            return 0

        async def _handle_one(broker_msg_id: str, msg: QueueMessage) -> None:
            try:
                await self.process_message_async(msg)
                await asyncio.to_thread(
                    self._broker.ack,
                    QUEUE_GENERAL,
                    self._consumer_group,
                    broker_msg_id,
                )
            except Exception as e:
                await asyncio.to_thread(
                    self._broker.nack,
                    QUEUE_GENERAL,
                    self._consumer_group,
                    broker_msg_id,
                    msg,
                    str(e),
                )

        await asyncio.gather(*(_handle_one(b_id, m) for b_id, m in messages))
        return len(messages)

    def run_once(self, timeout_ms: int = 1000) -> int:
        return asyncio.run(self.run_batch_async(count=1, timeout_ms=timeout_ms))
