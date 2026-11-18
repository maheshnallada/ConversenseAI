import asyncio
import logging
import time

from app.evaluation.service import EvaluationService
from app.queue.broker import MessageBroker, get_message_broker
from app.queue.limiter import ConcurrencyLimiter, get_concurrency_limiter
from app.queue.models import DEFAULT_CONSUMER_GROUP, QUEUE_EVALUATION, QueueMessage
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.stage_repo import StageRepository

logger = logging.getLogger(__name__)


class EvaluationWorker:
    """Worker responsible for LLM batch evaluations with native async concurrency."""

    def __init__(
        self,
        session_factory,
        broker: MessageBroker | None = None,
        limiter: ConcurrencyLimiter | None = None,
        worker_id: str = "eval-worker-1",
        consumer_group: str = DEFAULT_CONSUMER_GROUP,
    ) -> None:
        self._session_factory = session_factory
        self._broker = broker or get_message_broker()
        self._limiter = limiter or get_concurrency_limiter()
        self._worker_id = worker_id
        self._consumer_group = consumer_group

        self._eval_service = EvaluationService(session_factory)
        self._eval_repo = EvaluationRepository(session_factory)
        self._stage_repo = StageRepository(session_factory)

    async def process_message_async(self, message: QueueMessage) -> bool:
        tenant_id = message.tenant_id
        interaction_id = message.interaction_id
        start_time = time.time()

        await asyncio.to_thread(
            self._stage_repo.record_stage_start,
            tenant_id=tenant_id,
            interaction_id=interaction_id,
            stage_name="evaluation",
            max_retries=message.max_retries,
        )

        # Acquire concurrency token before calling LLM
        acquired = await asyncio.to_thread(self._limiter.acquire, timeout_s=30.0)
        if not acquired:
            raise TimeoutError("Could not acquire LLM concurrency permit within timeout")

        try:
            # Idempotency check: don't re-run evaluation if already completed
            existing_run = await asyncio.to_thread(
                self._eval_repo.get_latest_run,
                tenant_id,
                interaction_id,
            )
            if existing_run is None:
                await self._eval_service.evaluate_interaction_async(tenant_id, interaction_id)

            duration_ms = (time.time() - start_time) * 1000.0
            await asyncio.to_thread(
                self._stage_repo.record_stage_success,
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                stage_name="evaluation",
                duration_ms=duration_ms,
            )
            return True

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000.0
            logger.exception("Evaluation worker failed for %s: %s", interaction_id, e)
            is_dead_letter = (message.retry_count + 1) >= message.max_retries
            await asyncio.to_thread(
                self._stage_repo.record_stage_failure,
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                stage_name="evaluation",
                error_message=str(e),
                is_dead_letter=is_dead_letter,
                duration_ms=duration_ms,
            )
            raise
        finally:
            await asyncio.to_thread(self._limiter.release)

    def process_message(self, message: QueueMessage) -> bool:
        """Synchronous wrapper for process_message_async."""
        return asyncio.run(self.process_message_async(message))

    async def run_batch_async(self, count: int = 5, timeout_ms: int = 1000) -> int:
        """Pulls a batch of messages and executes evaluations concurrently."""
        messages = await asyncio.to_thread(
            self._broker.consume,
            QUEUE_EVALUATION,
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
                    QUEUE_EVALUATION,
                    self._consumer_group,
                    broker_msg_id,
                )
            except Exception as e:
                await asyncio.to_thread(
                    self._broker.nack,
                    QUEUE_EVALUATION,
                    self._consumer_group,
                    broker_msg_id,
                    msg,
                    str(e),
                )

        await asyncio.gather(*(_handle_one(b_id, m) for b_id, m in messages))
        return len(messages)

    def run_once(self, timeout_ms: int = 1000) -> int:
        return asyncio.run(self.run_batch_async(count=1, timeout_ms=timeout_ms))
