from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock

from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.ingestion.service import IngestionService
from app.queue.broker import InMemoryBroker
from app.queue.limiter import InMemoryConcurrencyLimiter
from app.queue.models import (
    QUEUE_ANALYTICS,
    QUEUE_DLQ,
    QUEUE_EVALUATION,
    QUEUE_GENERAL,
    QueueMessage,
)
from app.storage.db import create_session_factory, init_db
from app.storage.transcript_repo import TranscriptRepository
from app.workers.analytics_worker import AnalyticsWorker
from app.workers.evaluation_worker import EvaluationWorker
from app.workers.general_worker import GeneralWorker


@pytest.fixture
def session_factory(tmp_path):
    db_path = tmp_path / "test_workers.db"
    sf = create_session_factory(f"sqlite:///{db_path}")
    init_db(sf)
    return sf


def _seed_interaction(session_factory, tenant_id: str, interaction_id: str):
    now = datetime.now(timezone.utc)
    envelope = InteractionEnvelope(
        schema_version="1.0",
        tenant_id=tenant_id,
        interaction_id=interaction_id,
        started_at=now,
        domain_data={"end_reason": "not_answered", "meta": {"campaign_id": "test"}},
    )
    IngestionService(session_factory).ingest(envelope)
    turns = [
        TranscriptTurn(
            tenant_id=tenant_id,
            interaction_id=interaction_id,
            turn_index=1,
            speaker="agent",
            raw_text="Hello",
            normalized_text="Hello",
            start_s=0.0,
            end_s=1.0,
            duration_s=1.0,
            turn_id=f"{interaction_id}_turn_1",
        )
    ]
    TranscriptRepository(session_factory).save_turns(tenant_id, interaction_id, turns)
    return envelope


def test_general_worker_processes_and_fans_out(session_factory):
    tenant_id = "tenant-w"
    interaction_id = "call-w-1"
    _seed_interaction(session_factory, tenant_id, interaction_id)

    broker = InMemoryBroker()
    msg = QueueMessage(
        tenant_id=tenant_id,
        interaction_id=interaction_id,
        stage="general",
    )
    broker.publish(QUEUE_GENERAL, msg)

    worker = GeneralWorker(session_factory, broker=broker)
    processed = worker.run_once()
    assert processed == 1

    # General queue is now empty
    stats = broker.get_queue_stats()
    assert stats["queues"][QUEUE_GENERAL] == 0
    # Fans out to evaluation and analytics
    assert stats["queues"][QUEUE_EVALUATION] == 1
    assert stats["queues"][QUEUE_ANALYTICS] == 1


def test_evaluation_worker_processes_deterministic_call(session_factory):
    tenant_id = "tenant-eval"
    interaction_id = "call-eval-1"
    _seed_interaction(session_factory, tenant_id, interaction_id)

    broker = InMemoryBroker()
    msg = QueueMessage(
        tenant_id=tenant_id,
        interaction_id=interaction_id,
        stage="evaluation",
    )
    broker.publish(QUEUE_EVALUATION, msg)

    limiter = InMemoryConcurrencyLimiter(max_concurrency=2)
    worker = EvaluationWorker(session_factory, broker=broker, limiter=limiter)
    processed = worker.run_once()
    assert processed == 1

    stats = broker.get_queue_stats()
    assert stats["queues"][QUEUE_EVALUATION] == 0
    assert stats["queues"][QUEUE_DLQ] == 0


def test_analytics_worker_processes_message(session_factory):
    tenant_id = "tenant-a"
    interaction_id = "call-a-1"

    broker = InMemoryBroker()
    msg = QueueMessage(
        tenant_id=tenant_id,
        interaction_id=interaction_id,
        stage="analytics",
    )
    broker.publish(QUEUE_ANALYTICS, msg)

    worker = AnalyticsWorker(session_factory, broker=broker)
    processed = worker.run_once()
    assert processed == 1

    stats = broker.get_queue_stats()
    assert stats["queues"][QUEUE_ANALYTICS] == 0
