import asyncio
from datetime import datetime, timezone
import pytest

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
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.stage_repo import StageRepository
from app.storage.timeline_repo import TimelineRepository
from app.storage.transcript_repo import TranscriptRepository
from app.workers.evaluation_worker import EvaluationWorker
from app.workers.general_worker import GeneralWorker


@pytest.fixture
def session_factory(tmp_path):
    db_path = tmp_path / "test_async_w.db"
    sf = create_session_factory(f"sqlite:///{db_path}")
    init_db(sf)
    return sf


def _seed_call(session_factory, tenant_id: str, call_id: str):
    now = datetime.now(timezone.utc)
    envelope = InteractionEnvelope(
        schema_version="1.0",
        tenant_id=tenant_id,
        interaction_id=call_id,
        started_at=now,
        domain_data={"end_reason": "not_answered", "meta": {"campaign_id": "test"}},
    )
    IngestionService(session_factory).ingest(envelope)
    turns = [
        TranscriptTurn(
            tenant_id=tenant_id,
            interaction_id=call_id,
            turn_index=1,
            speaker="agent",
            raw_text="Hello",
            normalized_text="Hello",
            start_s=0.0,
            end_s=1.0,
            duration_s=1.0,
            turn_id=f"{call_id}_turn_1",
        )
    ]
    TranscriptRepository(session_factory).save_turns(tenant_id, call_id, turns)


@pytest.mark.anyio
async def test_general_worker_processes_batch_concurrently(session_factory):
    tenant_id = "tenant-async-gen"
    broker = InMemoryBroker()

    # Seed 3 calls
    for i in range(3):
        call_id = f"async-call-{i}"
        _seed_call(session_factory, tenant_id, call_id)
        broker.publish(QUEUE_GENERAL, QueueMessage(tenant_id=tenant_id, interaction_id=call_id, stage="general"))

    worker = GeneralWorker(session_factory, broker=broker)
    # Process batch of 3 concurrently
    processed = await worker.run_batch_async(count=3)
    assert processed == 3

    stats = broker.get_queue_stats()
    assert stats["queues"][QUEUE_GENERAL] == 0
    assert stats["queues"][QUEUE_EVALUATION] == 3
    assert stats["queues"][QUEUE_ANALYTICS] == 3

    # Verify all 3 timelines were reconstructed
    timeline_repo = TimelineRepository(session_factory)
    for i in range(3):
        assert timeline_repo.get_timeline(tenant_id, f"async-call-{i}") is not None


@pytest.mark.anyio
async def test_evaluation_worker_processes_batch_concurrently(session_factory):
    tenant_id = "tenant-async-eval"
    broker = InMemoryBroker()

    for i in range(3):
        call_id = f"eval-call-{i}"
        _seed_call(session_factory, tenant_id, call_id)
        broker.publish(QUEUE_EVALUATION, QueueMessage(tenant_id=tenant_id, interaction_id=call_id, stage="evaluation"))

    limiter = InMemoryConcurrencyLimiter(max_concurrency=5)
    worker = EvaluationWorker(session_factory, broker=broker, limiter=limiter)

    # Process batch of 3 concurrently
    processed = await worker.run_batch_async(count=3)
    assert processed == 3

    stats = broker.get_queue_stats()
    assert stats["queues"][QUEUE_EVALUATION] == 0
    assert stats["queues"][QUEUE_DLQ] == 0

    eval_repo = EvaluationRepository(session_factory)
    stage_repo = StageRepository(session_factory)
    for i in range(3):
        call_id = f"eval-call-{i}"
        assert eval_repo.get_latest_run(tenant_id, call_id) is not None
        stages = stage_repo.get_stages(tenant_id, call_id)
        assert any(s["stage_name"] == "evaluation" and s["status"] == "completed" for s in stages)
