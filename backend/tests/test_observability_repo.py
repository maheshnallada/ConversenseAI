import pytest
from sqlalchemy.pool import StaticPool

from app.domain.observability import InteractionMetrics, PercentilesResult
from app.observability.config import CostBreakdown
from app.storage.db import create_session_factory, init_db
from app.storage.observability_repo import ObservabilityRepository


def _factory():
    f = create_session_factory("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(f)
    return f


def _sample_metrics(interaction_id="call_01", cost=0.015, currency="USD", latency_samples=None):
    return InteractionMetrics(
        tenant_id="tenant_obs",
        interaction_id=interaction_id,
        recording_duration_s=60.0,
        telephony_duration_s=58.5,
        turn_count=10,
        agent_turn_count=6,
        customer_turn_count=4,
        first_agent_latency_s=1.2,
        response_latency_percentiles=PercentilesResult(avg=1.0, p50=0.9, p90=1.5, p95=1.8, p99=2.0),
        longest_silence_s=2.5,
        overlap_count=1,
        total_overlap_s=0.5,
        audio_missing=False,
        audio_silent=False,
        llm_provider="gemini",
        llm_model="gemini-3.5-flash-lite",
        input_tokens=1000,
        output_tokens=200,
        total_tokens=1200,
        response_latency_samples=latency_samples or [],
        cost_breakdown=CostBreakdown(
            llm_cost=0.0001,
            stt_cost=0.002,
            tts_cost=0.003,
            telephony_cost=0.01,
            total_cost=cost,
            currency=currency,
        ),
    )


def test_save_and_get_metrics():
    factory = _factory()
    repo = ObservabilityRepository(factory)

    metrics = _sample_metrics("call_01")
    repo.save_metrics(metrics)

    retrieved = repo.get_metrics("tenant_obs", "call_01")
    assert retrieved is not None
    assert retrieved.tenant_id == "tenant_obs"
    assert retrieved.interaction_id == "call_01"
    assert retrieved.recording_duration_s == 60.0
    assert retrieved.telephony_duration_s == 58.5
    assert retrieved.response_latency_percentiles.p50 == 0.9
    assert retrieved.response_latency_samples == []
    assert retrieved.cost_breakdown.total_cost == 0.015

    # Test idempotency (re-saving replaces cleanly)
    repo.save_metrics(metrics)
    retrieved2 = repo.get_metrics("tenant_obs", "call_01")
    assert retrieved2 is not None


def test_platform_summary_aggregation():
    factory = _factory()
    repo = ObservabilityRepository(factory)

    repo.save_metrics(_sample_metrics("call_01", cost=0.010))
    repo.save_metrics(_sample_metrics("call_02", cost=0.020))

    summary = repo.get_platform_summary("tenant_obs")
    assert summary.total_interactions == 2
    assert summary.total_recording_duration_s == 120.0
    assert summary.total_telephony_duration_s == 117.0
    assert summary.total_turns == 20
    assert summary.total_agent_turns == 12
    assert summary.total_customer_turns == 8
    assert round(summary.total_cost, 4) == 0.030
    assert summary.currency == "USD"


def test_platform_summary_aggregates_raw_latency_samples_and_currency():
    factory = _factory()
    repo = ObservabilityRepository(factory)
    repo.save_metrics(
        _sample_metrics("call_01", cost=0.010, currency="EUR", latency_samples=[1.0, 2.0, 100.0])
    )
    repo.save_metrics(
        _sample_metrics("call_02", cost=0.020, currency="EUR", latency_samples=[10.0])
    )

    summary = repo.get_platform_summary("tenant_obs")

    assert summary.overall_latency_percentiles.p50 == 6.0
    assert summary.currency == "EUR"
    assert summary.total_cost == 0.03


def test_platform_summary_marks_mixed_currency_totals_unavailable():
    factory = _factory()
    repo = ObservabilityRepository(factory)
    repo.save_metrics(_sample_metrics("call_usd", cost=0.010, currency="USD"))
    repo.save_metrics(_sample_metrics("call_eur", cost=0.020, currency="EUR"))

    summary = repo.get_platform_summary("tenant_obs")

    assert summary.currency is None
    assert summary.total_cost is None
    assert summary.cost_by_currency == {"USD": 0.01, "EUR": 0.02}


def test_empty_platform_summary_has_no_currency_or_total():
    repo = ObservabilityRepository(_factory())

    summary = repo.get_platform_summary("tenant_without_metrics")

    assert summary.currency is None
    assert summary.total_cost is None
    assert summary.cost_by_currency == {}

