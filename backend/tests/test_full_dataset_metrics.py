from pathlib import Path
import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import StaticPool

from app.observability.config import RateCardManager
from app.observability.service import ObservabilityService
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
    # Total tokens and cost are positive
    assert summary.total_input_tokens > 0
    assert summary.total_output_tokens > 0
    assert summary.total_cost > 0.0
    assert summary.currency == "USD"

