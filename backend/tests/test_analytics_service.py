import json
from datetime import datetime, timezone
import pytest
from sqlalchemy import text
from app.storage.db import create_session_factory, init_db
from app.storage.orm import EvaluationBatchRow, InteractionEventRow, InteractionRow
from app.analytics.service import AnalyticsService
from app.domain.evaluation import EvaluationBatchRecord, EvaluationRun
from app.domain.observability import InteractionMetrics, PercentilesResult
from app.observability.config import CostBreakdown
from app.storage.evaluation_repo import EvaluationRepository
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


def _evaluation_run(
    tenant_id,
    interaction_id,
    run_id,
    started_at,
    overall,
    outcome,
    compliance_status,
):
    batches = []
    for batch_name, parsed_output in (
        (
            "conversation_understanding",
            {
                "outcome": {"label": outcome},
                "sentiment": {"label": "Neutral"},
                "emotion": {"label": "Cooperative"},
            },
        ),
        (
            "conversation_quality",
            {
                "conversation_quality": {},
                "conversation_completeness": {"conversation_status": "COMPLETED"},
            },
        ),
        (
            "compliance_appointment",
            {
                "compliance": {
                    "rule_results": {
                        "NR001": {"status": compliance_status}
                    }
                }
            },
        ),
    ):
        batches.append(
            EvaluationBatchRecord(
                evaluation_id=f"{run_id}-{batch_name}",
                batch_name=batch_name,
                status="completed",
                model="test-model",
                prompt_version="1",
                schema_version="1",
                started_at=started_at,
                completed_at=started_at,
                input_tokens=None,
                output_tokens=None,
                raw_output=None,
                parsed_output=parsed_output,
                validation={},
                review_required=False,
                review_status="NOT_REQUIRED",
                review_reasons=[],
            )
        )
    return EvaluationRun(
        run_id=run_id,
        tenant_id=tenant_id,
        interaction_id=interaction_id,
        batches=batches,
        summary={"overall_assessment": overall},
        started_at=started_at,
        completed_at=started_at,
        review_required=False,
        review_reasons=[],
    )


def _cost_metrics(
    interaction_id,
    currency,
    cost,
    tenant_id="tenant_cost",
    latency=None,
    telephony_cost=None,
    input_tokens=None,
    output_tokens=None,
):
    percentiles = (
        PercentilesResult(
            avg=latency,
            p50=latency,
            p90=latency,
            p95=latency,
            p99=latency,
        )
        if latency is not None
        else PercentilesResult()
    )
    return InteractionMetrics(
        tenant_id=tenant_id,
        interaction_id=interaction_id,
        recording_duration_s=None,
        telephony_duration_s=None,
        turn_count=0,
        agent_turn_count=0,
        customer_turn_count=0,
        first_agent_latency_s=latency,
        response_latency_percentiles=percentiles,
        longest_silence_s=None,
        overlap_count=0,
        total_overlap_s=0.0,
        audio_missing=False,
        audio_silent=False,
        llm_provider=None,
        llm_model=None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=(
            input_tokens + output_tokens
            if input_tokens is not None and output_tokens is not None
            else None
        ),
        cost_breakdown=CostBreakdown(
            llm_cost=cost,
            stt_cost=None,
            tts_cost=None,
            telephony_cost=telephony_cost,
            total_cost=(
                cost + (telephony_cost or 0) if cost is not None else None
            ),
            currency=currency,
        ),
    )

@pytest.fixture
def analytics_service():
    service, factory = _isolated_service()
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        session.add(_interaction("health_campaign", "call_01", "completed"))
    EvaluationRepository(factory).save_run(
        _evaluation_run(
            "health_campaign",
            "call_01",
            "run-call-01",
            now,
            "Good",
            "Expert call booked",
            "NOT_DETECTED",
        )
    )
    ObservabilityRepository(factory).save_metrics(
        _cost_metrics(
            "call_01",
            "USD",
            0.02,
            tenant_id="health_campaign",
            latency=0.4,
            telephony_cost=0.01,
            input_tokens=12,
            output_tokens=8,
        )
    )
    return service

def test_overview_analytics(analytics_service):
    overview = analytics_service.get_overview_analytics(tenant_id="health_campaign")

    assert overview["total_interactions"] == 1
    assert overview["interaction_status_counts"]["completed"] == 1
    assert overview["metrics_available_interactions"] == 1
    assert "quality_distribution" not in overview

def test_quality_analytics(analytics_service):
    quality = analytics_service.get_quality_analytics(tenant_id="health_campaign")

    assert "outcomes" in quality
    assert "sentiment" in quality
    assert "emotion" in quality
    assert "overall_quality" in quality
    assert sum(quality["overall_quality"].values()) == 1

def test_cost_analytics(analytics_service):
    cost = analytics_service.get_cost_analytics(tenant_id="health_campaign")

    assert cost["total_cost_usd"] > 0
    assert cost["currency"] == "USD"
    assert cost["total_tokens"] > 0
    assert cost["telephony_cost_usd"] > 0

def test_interactions_page_pagination(analytics_service):
    page1 = analytics_service.get_interactions_page(tenant_id="health_campaign", page=1, page_size=10)

    assert page1["total"] == 1
    assert len(page1["items"]) == 1
    assert page1["page"] == 1
    assert page1["pages"] == 1

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

    assert overview["interaction_status_counts"] == {
        "completed": 1,
        "abandoned": 1,
        "failed": 1,
        "pending": 1,
        "unknown": 2,
    }


def test_analytics_uses_latest_versioned_run_not_archival_results():
    service, factory = _isolated_service()
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    current = datetime(2026, 1, 2, tzinfo=timezone.utc)
    with factory() as session:
        session.add(_interaction("tenant_latest", "call_latest", "completed"))
        session.execute(
            text(
                "CREATE TABLE evaluation_results "
                "(id INTEGER PRIMARY KEY, tenant_id TEXT, interaction_id TEXT, "
                "evaluator_id TEXT, evaluator_version TEXT, family TEXT, "
                "method TEXT, label TEXT, review_status TEXT, evidence_json TEXT, "
                "reason TEXT, details_json TEXT, created_at DATETIME)"
            )
        )
        session.execute(
            text(
                "INSERT INTO evaluation_results "
                "(tenant_id, interaction_id, evaluator_id, evaluator_version, "
                "family, method, label, review_status, evidence_json, reason, "
                "details_json, created_at) VALUES "
                "('tenant_latest', 'call_latest', 'legacy.quality', '9.0', "
                "'quality', 'deterministic', 'Good', 'PASSED', '[]', 'archived', "
                "'{}', :created_at), "
                "('tenant_latest', 'call_latest', 'legacy.compliance', '9.0', "
                "'compliance', 'deterministic', 'PASSED', 'PASSED', '[]', "
                "'archived', '{}', :created_at), "
                "('tenant_latest', 'call_latest', 'legacy.outcome', '9.0', "
                "'outcome', 'deterministic', 'Expert call booked', 'PASSED', "
                "'[]', 'archived', '{}', :created_at)"
            ),
            {"created_at": current.isoformat()},
        )
        session.commit()
    repo = EvaluationRepository(factory)
    repo.save_run(
        _evaluation_run(
            "tenant_latest",
            "call_latest",
            "run-old",
            old,
            "Good",
            "Expert call booked",
            "NOT_DETECTED",
        )
    )
    repo.save_run(
        _evaluation_run(
            "tenant_latest",
            "call_latest",
            "run-current",
            current,
            "Bad",
            "Not interested",
            "DETECTED",
        )
    )

    overview = service.get_overview_analytics("tenant_latest")
    quality = service.get_quality_analytics("tenant_latest")
    page = service.get_interactions_page("tenant_latest")

    assert overview["interaction_status_counts"] == {"completed": 1}
    assert "quality_distribution" not in overview
    assert quality["outcomes"] == {"Not interested": 1}
    assert quality["overall_quality"] == {"Bad": 1}
    assert page["items"][0]["quality"] == "Bad"
    assert page["items"][0]["outcome"] == "Not interested"
    assert page["items"][0]["evaluations_count"] == 3


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


def test_reliability_uses_persisted_interaction_statuses_and_failures_only():
    from app.storage.orm import InteractionTimelineRow

    service, factory = _isolated_service()
    with factory.begin() as session:
        session.add(_interaction("tenant_reliability", "call-failed", "failed"))
        session.add(_interaction("tenant_reliability", "call-complete", "completed"))
        session.add(
            InteractionTimelineRow(
                tenant_id="tenant_reliability",
                interaction_id="call-failed",
                total_duration_s=12.0,
                agent_turn_count=1,
                customer_turn_count=1,
                overlap_count=0,
                total_overlap_s=0.0,
                first_technical_failure_type="AGENT_PLAYBACK_CUT",
                first_technical_failure_turn=1,
                first_technical_failure_time_s=4.0,
                first_conversational_failure_type=None,
                first_conversational_failure_turn=None,
                first_conversational_failure_time_s=None,
                timeline_json=json.dumps(
                    {
                        "failures": [
                            {
                                "failure_type": "AGENT_PLAYBACK_CUT",
                                "category": "technical",
                                "turn_index": 1,
                                "time_s": 4.0,
                                "evidence": "playback metadata",
                            },
                            {
                                "failure_type": "CUSTOMER_INTERRUPTION",
                                "category": "conversational",
                                "turn_index": 2,
                                "time_s": 6.0,
                                "evidence": "overlap metadata",
                            },
                        ]
                    }
                ),
                created_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            InteractionEventRow(
                tenant_id="tenant_reliability",
                interaction_id="call-failed",
                event_id="event-failed",
                event_type="provider.call.failed",
                occurred_at=None,
                payload_json=json.dumps({"reason": "timeout"}),
                event_hash="event-failed-hash",
                created_at=datetime.now(timezone.utc),
            )
        )

    reliability = service.get_reliability_analytics("tenant_reliability")

    assert reliability["interaction_status_counts"] == {"failed": 1, "completed": 1}
    assert reliability["technical_failures"] == {"AGENT_PLAYBACK_CUT": 1}
    assert reliability["conversational_failures"] == {"CUSTOMER_INTERRUPTION": 1}
    assert reliability["supplied_event_failures"] == {"provider.call.failed": 1}
    assert reliability["interactions_with_failures"] == 1
    assert "quality_distribution" not in reliability


def test_usage_reports_missing_usage_as_unavailable():
    service, _ = _isolated_service()

    usage = service.get_usage_analytics("tenant_no_usage")

    assert usage["usage_available"] is False
    assert usage["input_tokens"] is None
    assert usage["output_tokens"] is None
    assert usage["estimated_cost"] is None


def test_usage_keeps_unpriced_estimate_unavailable_but_preserves_reported_tokens():
    service, factory = _isolated_service()
    ObservabilityRepository(factory).save_metrics(
        _cost_metrics(
            "call-unpriced",
            "USD",
            None,
            tenant_id="tenant_unpriced",
            input_tokens=100,
            output_tokens=50,
        )
    )

    usage = service.get_usage_analytics("tenant_unpriced")

    assert usage["usage_available"] is True
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 50
    assert usage["estimated_cost"] is None
    assert usage["cost_availability"] == "unavailable"


def test_usage_includes_completed_provider_reported_evaluation_batch_tokens():
    service, factory = _isolated_service()
    now = datetime.now(timezone.utc)
    EvaluationRepository(factory).save_run(
        _evaluation_run(
            "tenant_eval_usage",
            "call_eval_usage",
            "run-eval-usage",
            now,
            "Good",
            "Expert call booked",
            "NOT_DETECTED",
        )
    )
    with factory.begin() as session:
        rows = session.query(EvaluationBatchRow).filter_by(
            run_id="run-eval-usage"
        ).all()
        rows[0].input_tokens = 13
        rows[0].output_tokens = 8

    usage = service.get_usage_analytics("tenant_eval_usage")

    assert usage["usage_available"] is True
    assert usage["evaluation_input_tokens"] == 13
    assert usage["evaluation_output_tokens"] == 8
    assert usage["input_tokens"] == 13
    assert usage["output_tokens"] == 8

