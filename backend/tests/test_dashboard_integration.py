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


def test_dashboard_has_separate_observability_detail_and_analytics_routes(
    session_factory,
):
    app = create_app(session_factory)
    paths = {route.path for route in app.routes}

    assert "/api/v1/interactions/{interaction_id}/observability" in paths
    assert "/api/v1/analytics/overview" in paths
    assert "/api/v1/analytics/reliability" in paths
    assert "/api/v1/analytics/usage" in paths

    overview = _route(app, "/api/v1/analytics/overview", "GET")("tenant_dashboard")
    reliability = _route(app, "/api/v1/analytics/reliability", "GET")(
        "tenant_dashboard"
    )
    usage = _route(app, "/api/v1/analytics/usage", "GET")("tenant_dashboard")

    assert "quality_distribution" not in overview
    assert "interaction_status_counts" in reliability
    assert usage["usage_available"] is False


def test_interaction_list_filters_by_date_use_case_status_and_error_state(
    session_factory,
):
    def interaction_row(interaction_id, status, use_case, started_at):
        envelope = InteractionEnvelope(
            tenant_id="tenant_filters",
            interaction_id=interaction_id,
            schema_version="1.0",
            status=status,
            use_case=use_case,
            started_at=started_at,
        )
        return InteractionRow(
            tenant_id="tenant_filters",
            interaction_id=interaction_id,
            schema_version="1.0",
            payload_json=envelope.model_dump_json(),
            payload_hash=interaction_id,
            created_at=datetime.now(timezone.utc),
        )

    service_rows = [
        interaction_row(
            "call-error",
            "failed",
            "health_insurance",
            datetime(2026, 2, 1, tzinfo=timezone.utc),
        ),
        interaction_row(
            "call-old",
            "failed",
            "health_insurance",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        interaction_row(
            "call-other-usecase",
            "failed",
            "other",
            datetime(2026, 2, 1, tzinfo=timezone.utc),
        ),
        interaction_row(
            "call-no-error",
            "completed",
            "health_insurance",
            datetime(2026, 2, 1, tzinfo=timezone.utc),
        ),
        interaction_row(
            "call-ok",
            "completed",
            "health_insurance",
            datetime(2026, 2, 1, tzinfo=timezone.utc),
        ),
    ]
    with session_factory.begin() as session:
        session.add_all(service_rows)
        from app.storage.orm import InteractionTimelineRow

        session.add_all(
            [
                InteractionTimelineRow(
                    tenant_id="tenant_filters",
                    interaction_id="call-error",
                    total_duration_s=3.0,
                    agent_turn_count=1,
                    customer_turn_count=1,
                    overlap_count=0,
                    total_overlap_s=0.0,
                    first_technical_failure_type="AGENT_PLAYBACK_CUT",
                    first_technical_failure_turn=1,
                    first_technical_failure_time_s=2.0,
                    first_conversational_failure_type=None,
                    first_conversational_failure_turn=None,
                    first_conversational_failure_time_s=None,
                    timeline_json='{"failures":[{"category":"technical","failure_type":"AGENT_PLAYBACK_CUT"}]}',
                    created_at=datetime.now(timezone.utc),
                ),
                InteractionTimelineRow(
                    tenant_id="tenant_filters",
                    interaction_id="call-no-error",
                    total_duration_s=3.0,
                    agent_turn_count=1,
                    customer_turn_count=1,
                    overlap_count=0,
                    total_overlap_s=0.0,
                    first_technical_failure_type=None,
                    first_technical_failure_turn=None,
                    first_technical_failure_time_s=None,
                    first_conversational_failure_type=None,
                    first_conversational_failure_turn=None,
                    first_conversational_failure_time_s=None,
                    timeline_json='{"failures":[]}',
                    created_at=datetime.now(timezone.utc),
                ),
            ]
        )

    from fastapi.testclient import TestClient

    client = TestClient(create_app(session_factory))
    headers = {"X-Tenant-Id": "tenant_filters"}
    page = client.get(
        "/api/v1/interactions",
        headers=headers,
        params={
            "status": "failed",
            "started_after": "2026-01-31T00:00:00Z",
            "started_before": "2026-02-02T00:00:00Z",
            "use_case": "health_insurance",
            "error_state": "has_errors",
        },
    )
    assert page.status_code == 200
    assert [item["interaction_id"] for item in page.json()["items"]] == ["call-error"]
    no_error_page = client.get(
        "/api/v1/interactions",
        headers=headers,
        params={
            "started_after": "2026-01-31T00:00:00Z",
            "started_before": "2026-02-02T00:00:00Z",
            "use_case": "health_insurance",
            "error_state": "no_errors",
        },
    )
    assert no_error_page.status_code == 200
    assert [item["interaction_id"] for item in no_error_page.json()["items"]] == [
        "call-no-error"
    ]


def test_dashboard_has_call_import_surface_and_no_legacy_local_ingest():
    from pathlib import Path

    repository_root = Path(__file__).resolve().parents[2]
    client_source = (
        repository_root / "frontend" / "src" / "api" / "client.js"
    ).read_text(encoding="utf-8")
    drilldown_source = (
        repository_root / "frontend" / "src" / "views" / "DrillDownView.jsx"
    ).read_text(encoding="utf-8")
    app_source = (
        repository_root / "frontend" / "src" / "App.jsx"
    ).read_text(encoding="utf-8")
    sidebar_source = (
        repository_root / "frontend" / "src" / "components" / "Sidebar.jsx"
    ).read_text(encoding="utf-8")
    import_view_path = (
        repository_root / "frontend" / "src" / "views" / "CallImportView.jsx"
    )
    import_view_source = import_view_path.read_text(encoding="utf-8")
    topbar_source = (
        repository_root / "frontend" / "src" / "components" / "Topbar.jsx"
    ).read_text(encoding="utf-8")

    assert "getInteractionsList" not in client_source
    assert "api.getInteractionsPage(" in drilldown_source
    assert "IngestView" not in app_source
    assert "CallImportView" in app_source
    assert "import-calls" in sidebar_source
    assert "Import Calls" in sidebar_source
    assert "onIngestClick" not in topbar_source
    assert not (repository_root / "frontend" / "src" / "views" / "IngestView.jsx").exists()
    assert "Single call" in import_view_source
    assert "Folder batch" in import_view_source
    assert "Upload from computer" in import_view_source
    assert "Staged backend calls" in import_view_source
    assert "Retry failed calls" in import_view_source
    for legacy_api in (
        "getQuality",
        "getCost",
        "uploadZip",
        "processPath",
        "seedAll",
    ):
        assert legacy_api not in client_source


def test_timeline_turn_card_keeps_unknown_speaker_and_timing_unavailable():
    from pathlib import Path

    repository_root = Path(__file__).resolve().parents[2]
    source = (
        repository_root / "frontend" / "src" / "components" / "TimelineTurnCard.jsx"
    ).read_text(encoding="utf-8")

    assert "Unknown speaker" in source
    assert "Unavailable" in source
    assert "disabled={seekTarget === null}" in source
    assert "event.start_s ?? 0" not in source
    assert "event.end_s ?? 0" not in source
