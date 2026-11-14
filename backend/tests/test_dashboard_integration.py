from datetime import datetime, timezone

from app.api.app import HumanReviewSubmission, create_app
from app.domain.envelope import InteractionEnvelope
from app.domain.evaluation import EvaluationBatchRecord, EvaluationRun
from app.domain.golden import GoldenCallLabel
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.golden_repo import GoldenDatasetRepository
from app.storage.orm import InteractionRow


def _batch(evaluation_id, batch_name, parsed_output):
    now = datetime.now(timezone.utc)
    return EvaluationBatchRecord(
        evaluation_id=evaluation_id,
        batch_name=batch_name,
        status="completed",
        model="test-model",
        prompt_version="1",
        schema_version="1",
        started_at=now,
        completed_at=now,
        input_tokens=1,
        output_tokens=1,
        raw_output="{}",
        parsed_output=parsed_output,
        validation={"schema_valid": True, "evidence_valid": True, "issues": []},
        review_required=False,
        review_status="not_required",
        review_reasons=[],
    )


def _run():
    now = datetime.now(timezone.utc)
    batches = [
        _batch(
            "evaluation-understanding",
            "conversation_understanding",
            {
                "outcome": {"label": "Not interested"},
                "sentiment": {"label": "Neutral"},
                "emotion": {"label": "Neutral"},
            },
        ),
        _batch(
            "evaluation-quality",
            "conversation_quality",
            {
                "conversation_completeness": {
                    "conversation_status": "COMPLETED"
                }
            },
        ),
        _batch(
            "evaluation-compliance",
            "compliance_appointment",
            {
                "compliance": {
                    "rule_results": {
                        f"NR00{index}": {"status": "NOT_DETECTED"}
                        for index in range(1, 7)
                    },
                    "potential_violations": [],
                }
            },
        ),
    ]
    return EvaluationRun(
        run_id="run-dashboard",
        tenant_id="tenant_dashboard",
        interaction_id="call-dashboard",
        batches=batches,
        summary={
            "overall_assessment": "Good",
            "critical_issues": [],
            "dimension_assessments": {},
        },
        started_at=now,
        completed_at=now,
        review_required=False,
        review_reasons=[],
    )


def _route(app, path, method):
    return next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == path and method in route.methods
    )


def test_dashboard_reads_batched_run_reviews_and_explicit_benchmark_labels(
    session_factory,
):
    app = create_app(session_factory)
    envelope = InteractionEnvelope(
        tenant_id="tenant_dashboard",
        interaction_id="call-dashboard",
        schema_version="1.0",
    )
    with session_factory.begin() as session:
        session.add(
            InteractionRow(
                tenant_id=envelope.tenant_id,
                interaction_id=envelope.interaction_id,
                schema_version=envelope.schema_version,
                payload_json=envelope.model_dump_json(),
                payload_hash="dashboard-test",
                created_at=datetime.now(timezone.utc),
            )
        )

    run = _run()
    EvaluationRepository(session_factory).save_run(run)
    GoldenDatasetRepository(session_factory).save_many(
        [
            GoldenCallLabel(
                call_id="call-dashboard",
                what_happened="Call concluded",
                correct_outcome="Not interested",
                sentiment="Neutral",
                emotion="Neutral",
                overall="Good",
                conversation_status="COMPLETED",
                language_slice="en",
            )
        ]
    )

    evaluations = _route(
        app,
        "/api/v1/interactions/{interaction_id}/evaluations",
        "GET",
    )("call-dashboard", "tenant_dashboard")
    assert evaluations["run_id"] == "run-dashboard"
    assert {batch["batch_name"] for batch in evaluations["batches"]} == {
        "conversation_understanding",
        "conversation_quality",
        "compliance_appointment",
    }

    review = _route(
        app,
        "/api/v1/interactions/{interaction_id}/reviews",
        "POST",
    )(
        "call-dashboard",
        HumanReviewSubmission(
            evaluation_id="evaluation-understanding",
            reviewed_label="Not interested",
            reviewer_name="Dashboard test",
            review_decision="ACCEPTED",
        ),
        "tenant_dashboard",
    )
    assert review["evaluation_id"] == "evaluation-understanding"

    audit = _route(
        app,
        "/api/v1/interactions/{interaction_id}/reviews",
        "GET",
    )("call-dashboard", "tenant_dashboard")
    assert audit[0]["evaluation_id"] == "evaluation-understanding"

    benchmark = _route(app, "/api/v1/golden-dataset/benchmark", "GET")(
        "tenant_dashboard"
    )
    assert benchmark["dimension_metrics"]["conversation_status"]["support"] == 1
    assert benchmark["details"]["availability"]["language_slice"] == "available"
    assert "en" in benchmark["details"]["language_slice_metrics"]
