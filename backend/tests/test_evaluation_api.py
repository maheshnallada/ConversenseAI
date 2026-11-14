from pathlib import Path
from datetime import datetime, timedelta, timezone
import pytest
from app.api.app import (
    create_app,
    EvaluateInteractionRequest,
    HumanReviewSubmission,
)
from app.domain.evaluation import EvaluationBatchRecord, EvaluationRun
from app.storage.db import create_session_factory, init_db
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.orm import EvaluationResultRow

@pytest.fixture
def test_app():
    root = Path(__file__).resolve().parent.parent.parent
    db_path = root / "backend" / "conversense.sqlite3"
    factory = create_session_factory(f"sqlite:///{db_path}")
    init_db(factory)
    return create_app(factory)


def _run(run_id, started_at, batch_status="completed"):
    batch = EvaluationBatchRecord(
        evaluation_id=f"evaluation-{run_id}",
        batch_name="conversation_understanding",
        status=batch_status,
        model="test-model",
        prompt_version="1",
        schema_version="1",
        started_at=started_at,
        completed_at=started_at,
        input_tokens=2,
        output_tokens=3,
        raw_output="{}",
        parsed_output={"outcome": {"label": "Can't tell"}},
        validation={"schema_valid": True, "evidence_valid": True},
        review_required=False,
        review_status="NOT_REQUIRED",
        review_reasons=[],
        error_type="provider_error" if batch_status == "failed" else None,
    )
    return EvaluationRun(
        run_id=run_id,
        tenant_id="tenant_001",
        interaction_id="call_01",
        batches=[batch],
        summary={"overall_assessment": "Can't tell"},
        started_at=started_at,
        completed_at=started_at,
        review_required=False,
        review_reasons=[],
    )


def test_evaluate_endpoint_accepts_retry_source_and_returns_partial_run(
    session_factory, monkeypatch
):
    from app.api import app as api_module

    run = _run("run-retry", datetime.now(timezone.utc), batch_status="failed")

    class StubEvaluationService:
        def __init__(self, _session_factory):
            pass

        def evaluate_interaction(self, tenant_id, interaction_id, retry_from_run_id=None):
            assert (tenant_id, interaction_id, retry_from_run_id) == (
                "tenant_001",
                "call_01",
                "run-previous",
            )
            return run

    monkeypatch.setattr(api_module, "EvaluationService", StubEvaluationService)
    app = create_app(session_factory)
    route = next(
        route for route in app.routes
        if route.path == "/api/v1/interactions/{interaction_id}/evaluate"
    )

    result = route.endpoint(
        "call_01",
        "tenant_001",
        EvaluateInteractionRequest(retry_from_run_id="run-previous"),
    )

    assert result["run_id"] == "run-retry"
    assert result["batches"][0]["batch_name"] == "conversation_understanding"
    assert result["batches"][0]["status"] == "failed"
    assert result["summary"]["overall_assessment"] == "Can't tell"


def test_evaluations_endpoint_returns_latest_versioned_run_not_legacy_rows(
    session_factory, monkeypatch
):
    from app.api import app as api_module

    now = datetime.now(timezone.utc)
    repo = EvaluationRepository(session_factory)
    repo.save_run(_run("run-old", now - timedelta(minutes=1)))
    repo.save_run(_run("run-latest", now))
    with session_factory.begin() as session:
        session.add(
            EvaluationResultRow(
                tenant_id="tenant_001",
                interaction_id="call_01",
                evaluator_id="legacy.outcome",
                evaluator_version="1",
                family="outcome",
                method="deterministic",
                label="legacy",
                score=None,
                confidence=None,
                severity=None,
                review_status="PASSED",
                evidence_json="[]",
                reason="archived",
                details_json="{}",
                created_at=now,
            )
        )

    class StubEvaluationService:
        def __init__(self, _session_factory):
            pass

        def resolve_interaction_id(self, tenant_id, interaction_id):
            return interaction_id

    monkeypatch.setattr(api_module, "EvaluationService", StubEvaluationService)
    app = create_app(session_factory)
    route = next(
        route for route in app.routes
        if route.path == "/api/v1/interactions/{interaction_id}/evaluations"
    )

    result = route.endpoint("call_01", "tenant_001")

    assert result["run_id"] == "run-latest"
    assert [batch["batch_name"] for batch in result["batches"]] == [
        "conversation_understanding"
    ]
    assert "evaluator_id" not in result["batches"][0]


def test_review_endpoint_targets_a_versioned_batch(session_factory, monkeypatch):
    from app.api import app as api_module

    run = _run("run-review", datetime.now(timezone.utc))
    EvaluationRepository(session_factory).save_run(run)

    class StubEvaluationService:
        def __init__(self, _session_factory):
            pass

        def resolve_interaction_id(self, tenant_id, interaction_id):
            return interaction_id

    monkeypatch.setattr(api_module, "EvaluationService", StubEvaluationService)
    app = create_app(session_factory)
    route = next(
        route for route in app.routes
        if route.path == "/api/v1/interactions/{interaction_id}/reviews"
        and "POST" in route.methods
    )

    review = route.endpoint(
        "call_01",
        HumanReviewSubmission(
            evaluation_id=run.batches[0].evaluation_id,
            reviewed_label="accepted",
            reviewer_name="Reviewer",
            review_decision="ACCEPTED",
        ),
        "tenant_001",
    )

    assert review["evaluation_id"] == run.batches[0].evaluation_id
    assert review["review_decision"] == "ACCEPTED"


def test_api_routes_registered(test_app):
    routes = [r.path for r in test_app.routes]
    assert "/api/v1/interactions" in routes
    assert "/api/v1/interactions/{interaction_id}" in routes
    assert "/api/v1/interactions/{interaction_id}/evaluate" in routes
    assert "/api/v1/interactions/{interaction_id}/evaluations" in routes
    assert "/api/v1/interactions/process-and-evaluate" in routes

