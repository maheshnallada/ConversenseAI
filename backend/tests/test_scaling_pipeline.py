from datetime import datetime, timezone
import pytest

from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.ingestion.service import IngestionService
from app.queue.broker import InMemoryBroker
from app.queue.limiter import InMemoryConcurrencyLimiter
from app.queue.models import QUEUE_ANALYTICS, QUEUE_DLQ, QUEUE_EVALUATION, QUEUE_GENERAL
from app.queue.outbox_publisher import OutboxPublisher
from app.storage.db import create_session_factory, init_db
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.observability_repo import ObservabilityRepository
from app.storage.stage_repo import StageRepository
from app.storage.timeline_repo import TimelineRepository
from app.storage.transcript_repo import TranscriptRepository
from app.workers.analytics_worker import AnalyticsWorker
from app.workers.evaluation_worker import EvaluationWorker
from app.workers.general_worker import GeneralWorker


@pytest.fixture
def session_factory(tmp_path):
    db_path = tmp_path / "test_burst.db"
    sf = create_session_factory(f"sqlite:///{db_path}")
    init_db(sf)
    return sf


def test_end_to_end_burst_scaling_pipeline(session_factory):
    """
    Simulates a burst of 10 incoming calls:
    1. Ingestion writes interactions + transactional outbox records.
    2. OutboxPublisher sweeps records to broker queue (stream:general).
    3. GeneralWorker reconstructs timelines, computes metrics, and fans out to evaluation & analytics.
    4. EvaluationWorker and AnalyticsWorker consume their streams.
    5. Verifies end-to-end completion, stage tracking, and zero queue backlog.
    """
    tenant_id = "tenant-burst"
    num_calls = 10
    now = datetime.now(timezone.utc)

    # 1. Ingest burst of calls
    ingest_service = IngestionService(session_factory)
    transcript_repo = TranscriptRepository(session_factory)

    for i in range(num_calls):
        call_id = f"burst-call-{i}"
        envelope = InteractionEnvelope(
            schema_version="1.0",
            tenant_id=tenant_id,
            interaction_id=call_id,
            started_at=now,
            domain_data={"end_reason": "not_answered", "meta": {"campaign_id": "scaling-test"}},
        )
        ingest_service.ingest(envelope)
        turns = [
            TranscriptTurn(
                tenant_id=tenant_id,
                interaction_id=call_id,
                turn_index=1,
                speaker="agent",
                raw_text="Hello, thank you for calling.",
                normalized_text="Hello, thank you for calling.",
                start_s=0.0,
                end_s=2.0,
                duration_s=2.0,
                turn_id=f"{call_id}_turn_1",
            )
        ]
        transcript_repo.save_turns(tenant_id, call_id, turns)

    # 2. Setup broker and outbox publisher
    broker = InMemoryBroker()
    outbox = OutboxPublisher(session_factory, broker=broker)

    published = outbox.publish_pending(batch_size=50)
    assert published == num_calls
    assert broker.get_queue_stats()["queues"][QUEUE_GENERAL] == num_calls

    # 3. General Workers consume all general jobs
    general_worker = GeneralWorker(session_factory, broker=broker)
    general_processed = 0
    for _ in range(num_calls):
        general_processed += general_worker.run_once()
    assert general_processed == num_calls
    assert broker.get_queue_stats()["queues"][QUEUE_GENERAL] == 0
    assert broker.get_queue_stats()["queues"][QUEUE_EVALUATION] == num_calls
    assert broker.get_queue_stats()["queues"][QUEUE_ANALYTICS] == num_calls

    # 4. Evaluation Workers consume all evaluation jobs
    limiter = InMemoryConcurrencyLimiter(max_concurrency=5)
    eval_worker = EvaluationWorker(session_factory, broker=broker, limiter=limiter)
    eval_processed = 0
    for _ in range(num_calls):
        eval_processed += eval_worker.run_once()
    assert eval_processed == num_calls
    assert broker.get_queue_stats()["queues"][QUEUE_EVALUATION] == 0

    # 5. Analytics Workers consume all analytics jobs
    analytics_worker = AnalyticsWorker(session_factory, broker=broker)
    analytics_processed = 0
    for _ in range(num_calls):
        analytics_processed += analytics_worker.run_once()
    assert analytics_processed == num_calls
    assert broker.get_queue_stats()["queues"][QUEUE_ANALYTICS] == 0
    assert broker.get_queue_stats()["queues"][QUEUE_DLQ] == 0

    # 6. Verify database records
    timeline_repo = TimelineRepository(session_factory)
    obs_repo = ObservabilityRepository(session_factory)
    eval_repo = EvaluationRepository(session_factory)
    stage_repo = StageRepository(session_factory)

    for i in range(num_calls):
        call_id = f"burst-call-{i}"
        assert timeline_repo.get_timeline(tenant_id, call_id) is not None
        assert obs_repo.get_metrics(tenant_id, call_id) is not None
        assert eval_repo.get_latest_run(tenant_id, call_id) is not None

        stages = stage_repo.get_stages(tenant_id, call_id)
        stage_names = {s["stage_name"] for s in stages}
        assert "general" in stage_names
        assert "evaluation" in stage_names
        assert "analytics" in stage_names
        assert all(s["status"] == "completed" for s in stages)
