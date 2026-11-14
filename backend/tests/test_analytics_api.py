from pathlib import Path
import pytest
from app.storage.db import create_session_factory, init_db
from app.api.app import create_app, HumanReviewSubmission

@pytest.fixture
def app_instance():
    root = Path(__file__).resolve().parent.parent.parent
    db_path = root / "backend" / "conversense.sqlite3"
    factory = create_session_factory(f"sqlite:///{db_path}")
    init_db(factory)
    return create_app(factory)

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
    assert "/api/v1/use-cases" in routes
    assert "/api/v1/evaluators" in routes

def test_route_handlers_logic(app_instance):
    # Verify overview analytics handler
    overview_route = next(r for r in app_instance.routes if r.path == "/api/v1/analytics/overview")
    overview = overview_route.endpoint()
    assert overview["total_interactions"] == 50
    assert overview["total_cost_usd"] > 0

    # Verify quality analytics handler
    quality_route = next(r for r in app_instance.routes if r.path == "/api/v1/analytics/quality")
    quality = quality_route.endpoint()
    assert "outcomes" in quality

    # Verify interactions pagination handler
    interactions_route = next(r for r in app_instance.routes if r.path == "/api/v1/interactions" and "GET" in r.methods)
    page = interactions_route.endpoint(page=1, page_size=10, status=None, outcome=None, quality=None, search=None, x_tenant_id=None)
    assert page["total"] == 50
    assert len(page["items"]) == 10

    # Verify timeline handler for call_01
    timeline_route = next(r for r in app_instance.routes if r.path == "/api/v1/interactions/{interaction_id}/timeline")
    timeline = timeline_route.endpoint(interaction_id="call_01", x_tenant_id=None)
    assert "events" in timeline
    assert timeline["agent_turn_count"] > 0

    # Verify human review submission handler
    review_post = next(r for r in app_instance.routes if r.path == "/api/v1/interactions/{interaction_id}/reviews" and "POST" in r.methods)
    sub = HumanReviewSubmission(
        evaluator_id="outcome.intent",
        reviewed_label="Not interested",
        reviewer_name="QA Lead",
        review_decision="ACCEPTED",
        notes="Reviewed and accepted automated classification.",
    )
    res = review_post.endpoint(interaction_id="call_01", body=sub, x_tenant_id=None)
    assert res["reviewed_label"] == "Not interested"

    # Verify list reviews handler
    review_get = next(r for r in app_instance.routes if r.path == "/api/v1/interactions/{interaction_id}/reviews" and "GET" in r.methods)
    reviews_list = review_get.endpoint(interaction_id="call_01", x_tenant_id=None)
    assert len(reviews_list) >= 1
