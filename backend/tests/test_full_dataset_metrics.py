from pathlib import Path
import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import StaticPool

from app.observability.config import RateCardManager
from app.observability.service import ObservabilityService
from app.domain.envelope import InteractionEvent
from app.domain.transcript import TranscriptTurn
from app.storage.db import create_session_factory, init_db
from app.storage.orm import ObservabilityMetricsRow
from app.storage.observability_repo import ObservabilityRepository

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CALLS_DIR = PROJECT_ROOT / "backend" / "storage" / "artifacts" / "health_campaign"


def test_full_dataset_metrics_calculation():
    assert CALLS_DIR.exists()

    factory = create_session_factory("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(factory)

    rate_card = RateCardManager()
    service = ObservabilityService(session_factory=factory, rate_card=rate_card)
    repo = ObservabilityRepository(factory)

    call_folders = sorted(
        [d for d in CALLS_DIR.iterdir() if d.is_dir() and d.name.startswith("call_")],
        key=lambda d: d.name,
    )
    assert len(call_folders) == 50

    for folder in call_folders:
        service.process_call_folder(folder, tenant_id="tenant_metrics_test")

    with factory() as session:
        stored_count = session.scalar(select(func.count(ObservabilityMetricsRow.id)))
        assert stored_count == 50

    summary = repo.get_platform_summary("tenant_metrics_test")
    assert summary.total_interactions == 50
    assert summary.total_turns == 399
    assert summary.total_agent_turns == 230
    assert summary.total_customer_turns == 169
    assert summary.total_recording_duration_s == pytest.approx(1960.29)
    assert summary.total_telephony_duration_s > 2000.0
    # Two duration clocks are different
    assert summary.total_recording_duration_s != summary.total_telephony_duration_s
    # Token totals and total cost are reported across all priced interactions.
    assert summary.total_input_tokens > 0
    assert summary.total_output_tokens > 0
    assert summary.total_cost == pytest.approx(1.4626, abs=1e-4)
    assert summary.currency == "USD"


def test_observability_service_calculates_from_canonical_interaction_inputs():
    factory = create_session_factory(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(factory)
    service = ObservabilityService(factory)
    turn = TranscriptTurn(
        turn_id="turn-1",
        interaction_id="call-canonical",
        tenant_id="tenant-canonical",
        turn_index=0,
        speaker="agent",
        raw_text="Hello",
        normalized_text="hello",
        start_s=0.5,
        end_s=1.5,
        playback_spoken="heard",
    )
    event = InteractionEvent(
        event_id="event-1",
        event_type="call.completed",
        payload={"status": "completed"},
    )

    metrics = service.calculate_interaction(
        tenant_id="tenant-canonical",
        interaction_id="call-canonical",
        turns=[turn],
        events=[event],
        call_data={"meta": {}, "models": {}},
        calculation_version="2.1",
    )

    assert metrics.calculation_version == "2.1"
    assert metrics.event_types == ["call.completed"]
    assert metrics.playback_status_counts == {"heard": 1}

