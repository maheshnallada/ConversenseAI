import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from app.storage.db import create_session_factory, init_db
from app.storage.orm import EvaluationResultRow, InteractionRow
from app.analytics.service import AnalyticsService
from app.domain.observability import InteractionMetrics, PercentilesResult
from app.observability.config import CostBreakdown
from app.storage.observability_repo import ObservabilityRepository
from sqlalchemy.pool import StaticPool


def _isolated_service():
    factory = create_session_factory(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(factory)
    return AnalyticsService(factory), factory


def _interaction(tenant_id, interaction_id, status):
    return InteractionRow(
        tenant_id=tenant_id,
        interaction_id=interaction_id,
        schema_version="1.0",
        payload_json=json.dumps({"status": status}),
        payload_hash=interaction_id,
        created_at=datetime.now(timezone.utc),
    )


def _evaluation(tenant_id, interaction_id, family, version, label, created_at):
    return EvaluationResultRow(
        tenant_id=tenant_id,
        interaction_id=interaction_id,
        evaluator_id=f"{family}.test",
        evaluator_version=version,
        family=family,
        method="deterministic",
        label=label,
        score=0.5,
        confidence=0.8,
        severity="low",
        review_status="PASSED",
        evidence_json="[]",
        reason="test result",
        details_json="{}",
        created_at=created_at,
    )


def _cost_metrics(interaction_id, currency, cost):
    return InteractionMetrics(
        tenant_id="tenant_cost",
        interaction_id=interaction_id,
        recording_duration_s=None,
        telephony_duration_s=None,
        turn_count=0,
        agent_turn_count=0,
        customer_turn_count=0,
        first_agent_latency_s=None,
        response_latency_percentiles=PercentilesResult(),
        longest_silence_s=None,
        overlap_count=0,
        total_overlap_s=0.0,
        audio_missing=False,
        audio_silent=False,
        llm_provider=None,
        llm_model=None,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        cost_breakdown=CostBreakdown(
            llm_cost=cost,
            stt_cost=None,
            tts_cost=None,
            telephony_cost=None,
            total_cost=cost,
            currency=currency,
        ),
    )

@pytest.fixture
def analytics_service():
    root = Path(__file__).resolve().parent.parent.parent
    db_path = root / "backend" / "conversense.sqlite3"
    factory = create_session_factory(f"sqlite:///{db_path}")
    init_db(factory)
    return AnalyticsService(factory)

def test_overview_analytics(analytics_service):
    overview = analytics_service.get_overview_analytics(tenant_id="health_campaign")

    assert overview["total_interactions"] == 50
    assert overview["completed_interactions"] >= 0
    assert overview["abandoned_interactions"] >= 0
    assert "quality_distribution" in overview
    assert "compliance_findings" in overview
    assert overview["total_cost_usd"] > 0
    assert overview["avg_latency_s"] is not None

def test_quality_analytics(analytics_service):
    quality = analytics_service.get_quality_analytics(tenant_id="health_campaign")

    assert "outcomes" in quality
    assert "sentiment" in quality
    assert "emotion" in quality
    assert "overall_quality" in quality
    assert sum(quality["overall_quality"].values()) == 50

def test_cost_analytics(analytics_service):
    cost = analytics_service.get_cost_analytics(tenant_id="health_campaign")

    assert cost["total_cost_usd"] > 0
    assert cost["currency"] == "USD"
    assert cost["total_tokens"] > 0
    assert cost["telephony_cost_usd"] > 0

def test_interactions_page_pagination(analytics_service):
    page1 = analytics_service.get_interactions_page(tenant_id="health_campaign", page=1, page_size=10)

    assert page1["total"] == 50
    assert len(page1["items"]) == 10
    assert page1["page"] == 1
    assert page1["pages"] == 5

    first = page1["items"][0]
    assert "interaction_id" in first
    assert "status" in first
    assert "cost_usd" in first


def test_overview_classifies_noncompleted_statuses_separately():
    service, factory = _isolated_service()
    statuses = ["completed", "abandoned", "failed", "pending", "unknown", None]
    with factory() as session:
        for index, status in enumerate(statuses):
            session.add(_interaction("tenant_status", f"call_{index}", status))
        session.commit()

    overview = service.get_overview_analytics("tenant_status")

    assert overview["completed_interactions"] == 1
    assert overview["abandoned_interactions"] == 1
    assert overview["failed_interactions"] == 1
    assert overview["pending_interactions"] == 1
    assert overview["unknown_interactions"] == 2


def test_analytics_uses_latest_evaluation_per_interaction_and_family():
    service, factory = _isolated_service()
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    current = datetime(2026, 1, 2, tzinfo=timezone.utc)
    with factory() as session:
        session.add(_interaction("tenant_latest", "call_latest", "completed"))
        session.add_all(
            [
                _evaluation("tenant_latest", "call_latest", "quality", "1.0", "Good", old),
                _evaluation("tenant_latest", "call_latest", "quality", "2.0", "Bad", current),
                _evaluation("tenant_latest", "call_latest", "compliance", "1.0", "PASSED", old),
                _evaluation("tenant_latest", "call_latest", "compliance", "2.0", "FAILED", current),
                _evaluation("tenant_latest", "call_latest", "outcome", "1.0", "Expert call booked", old),
                _evaluation("tenant_latest", "call_latest", "outcome", "2.0", "Not interested", current),
            ]
        )
        session.commit()

    overview = service.get_overview_analytics("tenant_latest")
    quality = service.get_quality_analytics("tenant_latest")
    page = service.get_interactions_page("tenant_latest")

    assert overview["quality_distribution"] == {"Bad": 1}
    assert overview["compliance_findings"] == {"PASSED": 0, "FAILED": 1}
    assert overview["successful_outcomes"] == 0
    assert quality["outcomes"] == {"Not interested": 1}
    assert quality["overall_quality"] == {"Bad": 1}
    assert page["items"][0]["quality"] == "Bad"
    assert page["items"][0]["outcome"] == "Not interested"


def test_cost_analytics_does_not_sum_mixed_currencies():
    service, factory = _isolated_service()
    repository = ObservabilityRepository(factory)
    repository.save_metrics(_cost_metrics("call_usd", "USD", 0.01))
    repository.save_metrics(_cost_metrics("call_eur", "EUR", 0.02))

    cost = service.get_cost_analytics("tenant_cost")

    assert cost["total_cost"] is None
    assert cost["currency"] is None
    assert cost["cost_by_currency"] == {"USD": 0.01, "EUR": 0.02}
    assert cost["total_cost_usd"] is None


def test_cost_analytics_empty_result_has_no_currency_or_total():
    service, _ = _isolated_service()

    cost = service.get_cost_analytics("tenant_without_costs")

    assert cost["total_cost"] is None
    assert cost["currency"] is None
    assert cost["cost_by_currency"] == {}

