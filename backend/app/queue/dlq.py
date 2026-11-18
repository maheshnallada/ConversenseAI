import logging
from typing import Any

from sqlalchemy import select
from app.queue.broker import MessageBroker, get_message_broker
from app.queue.models import QUEUE_DLQ, QUEUE_GENERAL, QueueMessage
from app.storage.orm import PipelineStageRow

logger = logging.getLogger(__name__)


class DLQManager:
    def __init__(self, session_factory, broker: MessageBroker | None = None) -> None:
        self._session_factory = session_factory
        self._broker = broker or get_message_broker()

    def list_dead_letters(self, tenant_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            query = select(PipelineStageRow).where(PipelineStageRow.status == "dead_letter")
            if tenant_id:
                query = query.where(PipelineStageRow.tenant_id == tenant_id)
            query = query.order_by(PipelineStageRow.updated_at.desc()).limit(limit)
            rows = session.execute(query).scalars().all()

            return [
                {
                    "tenant_id": r.tenant_id,
                    "interaction_id": r.interaction_id,
                    "stage_name": r.stage_name,
                    "retry_count": r.retry_count,
                    "last_error": r.last_error,
                    "failed_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]

    def replay_interaction(
        self,
        tenant_id: str,
        interaction_id: str,
        target_stage: str = "general",
    ) -> bool:
        with self._session_factory() as session:
            rows = session.execute(
                select(PipelineStageRow).where(
                    PipelineStageRow.tenant_id == tenant_id,
                    PipelineStageRow.interaction_id == interaction_id,
                )
            ).scalars().all()

            for r in rows:
                r.status = "pending"
                r.retry_count = 0
                r.last_error = None
            session.commit()

        target_queue = QUEUE_GENERAL if target_stage == "general" else f"stream:{target_stage}"
        msg = QueueMessage(
            tenant_id=tenant_id,
            interaction_id=interaction_id,
            stage=target_stage,
            retry_count=0,
        )
        self._broker.publish(target_queue, msg)
        logger.info("Replayed interaction %s to %s", interaction_id, target_queue)
        return True
