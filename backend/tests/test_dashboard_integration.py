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

def test_full_dashboard_lifecycle(app_instance):
    # 1. Fetch Overview Analytics
    overview_handler = next(r for r in app_instance.routes if r.path == "/api/v1/analytics/overview").endpoint
    overview = overview_handler()
    assert overview["total_interactions"] == 50
    assert overview["successful_outcomes"] >= 0
    assert overview["quality_distribution"]["Good"] > 0
    assert overview["total_cost_usd"] > 0

    # 2. Fetch Cost Analytics
    cost_handler = next(r for r in app_instance.routes if r.path == "/api/v1/analytics/cost").endpoint
    cost = cost_handler()
    assert cost["currency"] == "USD"
    assert cost["total_tokens"] > 0
    assert "model_breakdown" in cost

    # 3. Explore & Paginate Interactions
    list_handler = next(r for r in app_instance.routes if r.path == "/api/v1/interactions" and "GET" in r.methods).endpoint
    page_res = list_handler(page=1, page_size=15, status=None, outcome=None, quality=None, search=None, x_tenant_id=None)
    assert page_res["total"] == 50
    assert len(page_res["items"]) == 15
    sample_call = page_res["items"][0]
    sample_id = sample_call["interaction_id"]

    # 4. Drill Down: Timeline
    timeline_handler = next(r for r in app_instance.routes if r.path == "/api/v1/interactions/{interaction_id}/timeline").endpoint
    timeline = timeline_handler(interaction_id=sample_id, x_tenant_id=None)
    assert "events" in timeline
    assert "total_duration_s" in timeline

    # 5. Drill Down: Evaluations
    evals_handler = next(r for r in app_instance.routes if r.path == "/api/v1/interactions/{interaction_id}/evaluations").endpoint
    evals = evals_handler(interaction_id=sample_id, x_tenant_id=None)
    assert len(evals) >= 5
    families = {e["family"] for e in evals}
    assert "compliance" in families
    assert "outcome" in families

    # 6. Human Review & Audit Trail
    review_post = next(r for r in app_instance.routes if r.path == "/api/v1/interactions/{interaction_id}/reviews" and "POST" in r.methods).endpoint
    rev_submission = HumanReviewSubmission(
        evaluator_id="outcome.intent",
        reviewed_label="Not interested",
        reviewer_name="Auditor-01",
        review_decision="ACCEPTED",
        notes="Verified dialogue ending.",
    )
    rev_res = review_post(interaction_id=sample_id, body=rev_submission, x_tenant_id=None)
    assert rev_res["reviewer_name"] == "Auditor-01"

    # 7. Check audit history
    review_get = next(r for r in app_instance.routes if r.path == "/api/v1/interactions/{interaction_id}/reviews" and "GET" in r.methods).endpoint
    audit = review_get(interaction_id=sample_id, x_tenant_id=None)
    assert len(audit) >= 1
    assert audit[0]["reviewer_name"] == "Auditor-01"

    # 8. Golden Benchmark Endpoint
    benchmark_handler = next(r for r in app_instance.routes if r.path == "/api/v1/golden-dataset/benchmark").endpoint
    benchmark = benchmark_handler(tenant_id="health_campaign")
    assert benchmark["total_interactions"] == 50
    assert "correct_outcome" in benchmark["dimension_metrics"]

