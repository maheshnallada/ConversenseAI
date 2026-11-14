from pathlib import Path
import pytest
from sqlalchemy.pool import StaticPool

from app.domain.envelope import InteractionEvent
from app.domain.transcript import TranscriptTurn
from app.reconstruction.processor import TranscriptProcessor
from app.reconstruction.reconstructor import TimelineReconstructor
from app.storage.db import create_session_factory, init_db
from app.storage.timeline_repo import TimelineRepository

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CALLS_DIR = PROJECT_ROOT / "backend" / "storage" / "artifacts" / "health_campaign"


def _factory():
    f = create_session_factory("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(f)
    return f


def test_reconstruct_call_01():
    call_01_dir = CALLS_DIR / "call_01"
    processor = TranscriptProcessor()
    turns = processor.process_folder(call_01_dir, tenant_id="tenant_rec")

    reconstructor = TimelineReconstructor()
    timeline = reconstructor.reconstruct(
        tenant_id="tenant_rec",
        interaction_id="call_01_id",
        turns=turns,
        call_metadata={"agent_wav_count": 4, "end_reason": "ended"},
    )

    assert timeline.tenant_id == "tenant_rec"
    assert timeline.interaction_id == "call_01_id"
    assert timeline.agent_turn_count == 4
    assert timeline.customer_turn_count == 3
    assert len(timeline.events) >= 7

    # In call_01, turn 2 is cut -> AGENT_PLAYBACK_CUT is a technical failure
    assert timeline.first_technical_failure is not None
    assert timeline.first_technical_failure.failure_type == "PLAYBACK_METADATA_MISMATCH"


def test_timeline_repository_save_and_get():
    factory = _factory()
    repo = TimelineRepository(factory)

    call_01_dir = CALLS_DIR / "call_01"
    processor = TranscriptProcessor()
    turns = processor.process_folder(call_01_dir, tenant_id="tenant_rec")

    reconstructor = TimelineReconstructor()
    timeline = reconstructor.reconstruct(
        tenant_id="tenant_rec",
        interaction_id="call_01_id",
        turns=turns,
        call_metadata={"agent_wav_count": 4, "end_reason": "ended"},
    )

    repo.save_timeline(timeline)
    retrieved = repo.get_timeline("tenant_rec", "call_01_id")

    assert retrieved is not None
    assert retrieved.tenant_id == "tenant_rec"
    assert retrieved.interaction_id == "call_01_id"
    assert retrieved.agent_turn_count == 4
    assert retrieved.customer_turn_count == 3
    assert len(retrieved.events) == len(timeline.events)
    assert retrieved.reconciliation == timeline.reconciliation
    assert retrieved.failures == timeline.failures
    assert (
        retrieved.technical_failure_ordering_unknown
        == timeline.technical_failure_ordering_unknown
    )

    # Test idempotency (re-saving replaces cleanly)
    repo.save_timeline(timeline)
    retrieved2 = repo.get_timeline("tenant_rec", "call_01_id")
    assert retrieved2 is not None


def test_reconstruction_keeps_unknown_duration_and_supplied_event_evidence():
    turn = TranscriptTurn(
        turn_id="turn-1",
        interaction_id="call-unknown",
        tenant_id="tenant-rec",
        turn_index=0,
        speaker="agent",
        raw_text="Hello",
        normalized_text="hello",
    )
    event = InteractionEvent(
        event_id="event-1",
        event_type="vendor.custom.event",
        payload={"value": "preserve"},
    )

    timeline = TimelineReconstructor().reconstruct(
        tenant_id="tenant-rec",
        interaction_id="call-unknown",
        turns=[turn],
        events=[event],
    )

    assert timeline.total_duration_s is None
    assert timeline.reconciliation is not None
    assert timeline.reconciliation.state == "unknown"
    assert timeline.reconciliation.review_required is False
    assert timeline.reconciliation.timestamp_quality == "unknown"
    assert timeline.reconciliation.source_events[0]["event_type"] == "vendor.custom.event"
    assert timeline.reconciliation.source_events[0]["payload"] == {"value": "preserve"}

    repository = TimelineRepository(_factory())
    repository.save_timeline(timeline)
    persisted = repository.get_timeline("tenant-rec", "call-unknown")

    assert persisted is not None
    assert persisted.total_duration_s is None
    assert persisted.reconciliation == timeline.reconciliation
    assert persisted.failures == timeline.failures

