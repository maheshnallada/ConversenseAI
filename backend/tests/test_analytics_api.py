import pytest
from app.api.app import create_app

@pytest.fixture
def app_instance(session_factory):
    return create_app(session_factory)

def test_section_11_routes_exist(app_instance):
    routes = [r.path for r in app_instance.routes]

    # Required Section 11 endpoints
    assert "/api/v1/analytics/overview" in routes
    assert "/api/v1/analytics/quality" in routes
    assert "/api/v1/analytics/cost" in routes
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

    quality_route = next(r for r in app_instance.routes if r.path == "/api/v1/analytics/quality")
    quality = quality_route.endpoint(tenant_id="health_campaign")
    assert "outcomes" in quality

    interactions_route = next(r for r in app_instance.routes if r.path == "/api/v1/interactions" and "GET" in r.methods)
    page = interactions_route.endpoint(page=1, page_size=10, status=None, outcome=None, quality=None, search=None, tenant_id="health_campaign")
    assert page["total"] == 0
    assert page["items"] == []
