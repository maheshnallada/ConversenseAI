import pytest
from app.api.app import create_app

@pytest.fixture
def app_instance(session_factory):
    return create_app(session_factory)

def test_section_11_routes_exist(app_instance):
    routes = [r.path for r in app_instance.routes]

    # Required Section 11 endpoints
    assert "/api/v1/analytics/overview" in routes
    assert "/api/v1/analytics/reliability" in routes
    assert "/api/v1/analytics/usage" in routes
    assert "/api/v1/interactions/{interaction_id}/observability" in routes
    assert "/api/v1/interactions" in routes
    assert "/api/v1/interactions/{interaction_id}" in routes
    assert "/api/v1/interactions/{interaction_id}/timeline" in routes
    assert "/api/v1/interactions/{interaction_id}/audio" in routes
    assert "/api/v1/interactions/{interaction_id}/reviews" in routes
    assert "/api/v1/use-cases" not in routes
    assert "/api/v1/evaluators" not in routes

def test_route_handlers_logic(app_instance):
    overview_route = next(r for r in app_instance.routes if r.path == "/api/v1/analytics/overview")
    overview = overview_route.endpoint(tenant_id="health_campaign")
    assert overview["total_interactions"] == 0

    reliability_route = next(r for r in app_instance.routes if r.path == "/api/v1/analytics/reliability")
    reliability = reliability_route.endpoint(tenant_id="health_campaign")
    assert "interaction_status_counts" in reliability

    usage_route = next(r for r in app_instance.routes if r.path == "/api/v1/analytics/usage")
    usage = usage_route.endpoint(tenant_id="health_campaign")
    assert usage["usage_available"] is False

    interactions_route = next(r for r in app_instance.routes if r.path == "/api/v1/interactions" and "GET" in r.methods)
    page = interactions_route.endpoint(page=1, page_size=10, status=None, outcome=None, quality=None, search=None, tenant_id="health_campaign")
    assert page["total"] == 0
    assert page["items"] == []


def test_observability_detail_returns_versioned_metrics_when_present(
    app_instance,
    session_factory,
):
    from app.domain.observability import InteractionMetrics, PercentilesResult
    from app.observability.config import CostBreakdown
    from app.storage.observability_repo import ObservabilityRepository
    from fastapi.testclient import TestClient

    client = TestClient(app_instance)
    created = client.post(
        "/api/v1/interactions",
        headers={"X-Tenant-Id": "tenant-metrics"},
        json={
            "tenant_id": "tenant-metrics",
            "interaction_id": "call-metrics",
            "schema_version": "1.0",
        },
    )
    assert created.status_code == 201
    metrics = InteractionMetrics(
        tenant_id="tenant-metrics",
        interaction_id="call-metrics",
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
        audio_missing=None,
        audio_silent=None,
        llm_provider=None,
        llm_model=None,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        cost_breakdown=CostBreakdown(None, None, None, None, None, "UNKNOWN"),
        calculation_version="2.1",
        rate_card_version=None,
        timestamp_quality="unknown",
    )
    ObservabilityRepository(session_factory).save_metrics(metrics)

    response = client.get(
        "/api/v1/interactions/call-metrics/observability",
        headers={"X-Tenant-Id": "tenant-metrics"},
    )

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["metrics"]["calculation_version"] == "2.1"
    assert response.json()["metrics"]["timestamp_quality"] == "unknown"


def test_observability_detail_requires_tenant_scoped_canonical_interaction(
    app_instance,
):
    from fastapi.testclient import TestClient

    client = TestClient(app_instance)
    tenant_a_interaction = client.post(
        "/api/v1/interactions",
        headers={"X-Tenant-Id": "tenant-a"},
        json={
            "tenant_id": "tenant-a",
            "interaction_id": "call-a",
            "schema_version": "1.0",
        },
    )
    assert tenant_a_interaction.status_code == 201

    missing = client.get(
        "/api/v1/interactions/missing/observability",
        headers={"X-Tenant-Id": "tenant-a"},
    )
    other_tenant = client.get(
        "/api/v1/interactions/call-a/observability",
        headers={"X-Tenant-Id": "tenant-b"},
    )
    unauthenticated = client.get("/api/v1/interactions/call-a/observability")

    assert missing.status_code == 404
    assert other_tenant.status_code == 404
    assert unauthenticated.status_code == 401
