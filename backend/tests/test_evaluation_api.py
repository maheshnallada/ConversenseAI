from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.api.app import (
    create_app,
    EvaluateInteractionRequest,
    HumanReviewSubmission,
)
from app.domain.envelope import InteractionEnvelope
from app.domain.evaluation import EvaluationBatchRecord, EvaluationRun
from app.evaluation.service import EvaluationService
from app.storage.evaluation_repo import EvaluationRepository

@pytest.fixture
def test_app(session_factory):
    return create_app(session_factory)


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


def test_evaluate_endpoint_uses_default_interaction_namespace(session_factory, monkeypatch):
    from app.api import app as api_module

    seen = {}

    class StubEvaluationService:
        def __init__(self, _session_factory):
            pass

        def evaluate_interaction(self, tenant_id, interaction_id, retry_from_run_id=None):
            seen["tenant_id"] = tenant_id
            seen["interaction_id"] = interaction_id
            seen["retry_from_run_id"] = retry_from_run_id
            return _run("run-default", datetime.now(timezone.utc))

    monkeypatch.setattr(api_module, "EvaluationService", StubEvaluationService)
    app = create_app(session_factory)
    route = next(
        route for route in app.routes
        if route.path == "/api/v1/interactions/{interaction_id}/evaluate"
    )

    result = route.endpoint(
        "call_01",
        "tenant_001",
        EvaluateInteractionRequest(),
    )

    assert seen == {
        "tenant_id": "tenant_001",
        "interaction_id": "call_01",
        "retry_from_run_id": None,
    }
    assert result["run_id"] == "run-default"


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
    session_factory,
):
    now = datetime.now(timezone.utc)
    repo = EvaluationRepository(session_factory)
    repo.save_run(_run("run-old", now - timedelta(minutes=1)))
    repo.save_run(_run("run-latest", now))
    with session_factory.begin() as session:
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
                "('tenant_001', 'call_01', 'legacy.outcome', '1', 'outcome', "
                "'deterministic', 'legacy', 'PASSED', '[]', 'archived', '{}', "
                ":created_at)"
            ),
            {"created_at": now.isoformat()},
        )

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


def test_evaluations_endpoint_returns_empty_when_no_run_exists(session_factory):
    app = create_app(session_factory)
    route = next(
        route for route in app.routes
        if route.path == "/api/v1/interactions/{interaction_id}/evaluations"
    )

    assert route.endpoint("call_without_run", "tenant_001") is None


def test_review_endpoint_targets_a_versioned_batch(session_factory):
    run = _run("run-review", datetime.now(timezone.utc))
    EvaluationRepository(session_factory).save_run(run)

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


def test_review_endpoint_returns_404_for_missing_evaluation(test_app):
    response = TestClient(test_app, raise_server_exceptions=False).post(
        "/api/v1/interactions/call_01/reviews",
        headers={"X-Tenant-Id": "tenant_001"},
        json={
            "evaluation_id": "missing-evaluation",
            "reviewed_label": "accepted",
            "reviewer_name": "Reviewer",
            "review_decision": "ACCEPTED",
        },
    )

    assert response.status_code == 404


def test_api_routes_registered(test_app):
    routes = [r.path for r in test_app.routes]
    assert "/api/v1/interactions" in routes
    assert "/api/v1/interactions/{interaction_id}" in routes
    assert "/api/v1/interactions/{interaction_id}/evaluate" in routes
    assert "/api/v1/interactions/{interaction_id}/evaluations" in routes
    assert "/api/v1/interactions/process-and-evaluate" not in routes
    assert "/api/v1/evaluators" not in routes


def test_review_required_compliance_batch_does_not_drive_appointment_validation(
    session_factory,
):
    started_at = datetime.now(timezone.utc)
    batch = EvaluationBatchRecord(
        evaluation_id="evaluation-review",
        batch_name="compliance_appointment",
        status="review_required",
        model="test-model",
        prompt_version="1",
        schema_version="1",
        started_at=started_at,
        completed_at=started_at,
        input_tokens=None,
        output_tokens=None,
        raw_output="{}",
        parsed_output={
            "compliance": {
                "rule_results": {
                    f"NR00{index}": {
                        "status": "NOT_DETECTED",
                        "evidence_line": None,
                        "quote": "",
                        "reason": "",
                    }
                    for index in range(1, 7)
                },
                "potential_violations": [],
            },
            "appointment_interpretation": {
                "appointment_type": "EXPERT_CALL",
                "consent_status": "EXPLICIT",
                "consent_evidence_line": None,
                "consent_quote": "",
                "agent_proposal_line": None,
                "agent_proposal_quote": "",
                "date_text": None,
                "time_text": None,
                "interpreted_date": None,
                "interpreted_time": None,
                "interpretation_reason": "No verified consent evidence.",
            },
        },
        validation={"schema_valid": True, "evidence_valid": False},
        review_required=True,
        review_status="required",
        review_reasons=["appointment consent evidence is missing"],
    )

    result = EvaluationService(session_factory)._derive_appointment_validation(
        InteractionEnvelope(
            tenant_id="tenant-1",
            interaction_id="interaction-1",
            schema_version="1.0",
        ),
        [batch],
    )

    assert result is None
