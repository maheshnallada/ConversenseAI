from pathlib import Path
from sqlalchemy.pool import StaticPool
from app.api.app import create_app
from app.storage.db import create_session_factory, init_db


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_evaluation_card_uses_batch_review_state_and_never_renders_score_or_confidence():
    source = (
        REPOSITORY_ROOT / "frontend" / "src" / "components" / "EvaluationCard.jsx"
    ).read_text(encoding="utf-8")

    assert "evaluation.batch_name" in source
    assert "evaluation.validation" in source
    assert "evaluation.review_reasons" in source
    assert "evaluation.score" not in source
    assert "evaluation.confidence" not in source
    assert "Score:" not in source
    assert "Confidence:" not in source


def test_drilldown_consumes_evaluation_run_and_renders_all_batches():
    source = (
        REPOSITORY_ROOT / "frontend" / "src" / "views" / "DrillDownView.jsx"
    ).read_text(encoding="utf-8")

    assert "evaluationRun?.batches" in source
    assert "evaluationRun?.summary" in source
    assert "api.evaluate(" in source
    assert "selectedCallId," in source
    assert "api.getObservability(" in source
    assert "Technical observability" in source
    assert "Semantic evaluation" in source
    assert "observabilityData?.available" in source
    assert "|| 'heard'" not in source


def test_overview_reads_operational_overview_reliability_and_usage_separately():
    source = (
        REPOSITORY_ROOT / "frontend" / "src" / "views" / "OverviewView.jsx"
    ).read_text(encoding="utf-8")

    assert "api.getOverview()" in source
    assert "api.getReliability()" in source
    assert "api.getUsage()" in source
    assert "api.getQuality()" not in source
    assert "quality_distribution" not in source
    assert "Unavailable" in source


def test_interactions_view_exposes_design_supported_filters():
    source = (
        REPOSITORY_ROOT / "frontend" / "src" / "views" / "InteractionsView.jsx"
    ).read_text(encoding="utf-8")

    for filter_name in (
        "started_after",
        "started_before",
        "use_case",
        "status",
        "outcome",
        "error_state",
    ):
        assert filter_name in source


def test_call_import_results_render_processing_status_and_safe_stage_errors():
    source = (
        REPOSITORY_ROOT / "frontend" / "src" / "views" / "CallImportView.jsx"
    ).read_text(encoding="utf-8")

    for processing_field in (
        "call.processing.transcript_turns",
        "call.processing.timeline_status",
        "call.processing.observability_status",
        "call.processing.evaluation_status",
        "call.processing.evaluation_run_id",
    ):
        assert processing_field in source
    assert "error.stage" in source
    assert "error.message" in source
    assert "Inspect call" in source
    assert "does not run evaluation" not in source


def test_timeline_turn_card_does_not_infer_heard_without_playback_metadata():
    source = (
        REPOSITORY_ROOT
        / "frontend"
        / "src"
        / "components"
        / "TimelineTurnCard.jsx"
    ).read_text(encoding="utf-8")

    assert "deliveryStatus = event.delivery_status || event.metadata?.playback_spoken || 'heard'" not in source
    assert "mismatch" in source
    assert "unknown" in source


def test_timeline_markers_do_not_infer_zero_duration_from_missing_evidence():
    source = (
        REPOSITORY_ROOT
        / "frontend"
        / "src"
        / "components"
        / "TimelineMarker.jsx"
    ).read_text(encoding="utf-8")

    assert "event.duration_s ? event.duration_s.toFixed(1) : '0.0'" not in source
    assert "Unavailable" in source


def test_missing_failure_evidence_does_not_render_as_success():
    source = (
        REPOSITORY_ROOT / "frontend" / "src" / "views" / "DrillDownView.jsx"
    ).read_text(encoding="utf-8")

    assert "if (!str || str.toLowerCase() === 'none') return 'None';" not in source
    assert "timeline.first_technical_failure ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'" not in source
    assert "timeline.first_conversational_failure ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'" not in source
    assert "return 'Unavailable';" in source


def test_review_modal_submits_batch_evaluation_id():
    source = (
        REPOSITORY_ROOT / "frontend" / "src" / "components" / "ReviewModal.jsx"
    ).read_text(encoding="utf-8")

    assert "evaluation_id:" in source
    assert "evaluation.evaluation_id" in source
    assert "evaluator_id:" not in source


def test_evaluation_card_renders_quotes_from_each_structured_batch_shape():
    source = (
        REPOSITORY_ROOT / "frontend" / "src" / "components" / "EvaluationCard.jsx"
    ).read_text(encoding="utf-8")

    for field in (
        "customer_quote",
        "agent_quote",
        "consent_quote",
        "agent_proposal_quote",
    ):
        assert field in source


def test_drilldown_counts_detected_compliance_rules_from_rule_results():
    source = (
        REPOSITORY_ROOT / "frontend" / "src" / "views" / "DrillDownView.jsx"
    ).read_text(encoding="utf-8")

    assert "Object.values(compliance || {})" in source
    assert "Detected compliance issues:" in source


def test_benchmark_uses_explicit_label_availability_without_seeding_or_thresholds():
    source = (
        REPOSITORY_ROOT / "frontend" / "src" / "views" / "BenchmarkView.jsx"
    ).read_text(encoding="utf-8")
    client_source = (
        REPOSITORY_ROOT / "frontend" / "src" / "api" / "client.js"
    ).read_text(encoding="utf-8")

    assert "benchmark.details?.availability?.conversation_status" in source
    assert "benchmark.details?.availability?.language_slice" in source
    assert "language_slice_metrics" in source
    assert "const result = await api.importGolden()" in source
    assert "setBenchmark(result.report)" in source
    for field in (
        "records_seen",
        "labels_imported",
        "test_records_excluded",
        "evaluations_created",
        "evaluations_reused",
        "evaluations_failed",
    ):
        assert f"importResult.{field}" in source
    assert "importResult.records" in source
    assert "record.call_id" in source
    assert "record.error" in source
    assert "request('/golden-dataset/import'" in client_source
    assert "request('/golden-dataset/benchmark'" in client_source
    assert "@typedef {Object} GoldenBenchmarkImportResult" in client_source
    assert "@returns {Promise<BenchmarkReport>}" in client_source
    assert "api.seedAll" not in source
    assert "Release threshold" not in source


def test_evaluator_configuration_surface_is_absent():
    assert not (
        REPOSITORY_ROOT / "frontend" / "src" / "views" / "EvaluatorsView.jsx"
    ).exists()
    app_source = (REPOSITORY_ROOT / "frontend" / "src" / "App.jsx").read_text(
        encoding="utf-8"
    )
    sidebar_source = (
        REPOSITORY_ROOT / "frontend" / "src" / "components" / "Sidebar.jsx"
    ).read_text(encoding="utf-8")
    topbar_source = (
        REPOSITORY_ROOT / "frontend" / "src" / "components" / "Topbar.jsx"
    ).read_text(encoding="utf-8")
    client_source = (REPOSITORY_ROOT / "frontend" / "src" / "api" / "client.js").read_text(
        encoding="utf-8"
    )
    api_source = (REPOSITORY_ROOT / "backend" / "app" / "api" / "app.py").read_text(
        encoding="utf-8"
    )

    assert "EvaluatorsView" not in app_source
    assert "'evaluators'" not in sidebar_source
    assert "evaluators:" not in topbar_source
    assert "getEvaluators" not in client_source
    assert '"/api/v1/evaluators"' not in api_source
    assert "getUseCases" not in client_source
    assert '"/api/v1/use-cases"' not in api_source


def test_serve_dashboard_index_html():
    factory = create_session_factory(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(factory)
    app = create_app(factory)

    # Check that root route exists
    root_route = next((r for r in app.routes if getattr(r, "path", None) == "/"), None)
    assert root_route is not None

    # Call the endpoint directly
    response = root_route.endpoint()
    assert response.status_code == 200
    assert Path(response.path).exists()
    content = Path(response.path).read_text(encoding="utf-8")
    assert "Conversense AI" in content
    assert "id=\"root\"" in content


def test_serve_dashboard_alias():
    factory = create_session_factory(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(factory)
    app = create_app(factory)

    dash_route = next((r for r in app.routes if getattr(r, "path", None) == "/dashboard"), None)
    assert dash_route is not None

    response = dash_route.endpoint()
    assert response.status_code == 200
    content = Path(response.path).read_text(encoding="utf-8")
    assert "id=\"root\"" in content


def test_static_assets_mounted():
    factory = create_session_factory(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(factory)
    app = create_app(factory)

    static_mount = next((r for r in app.routes if getattr(r, "path", None) == "/static"), None)
    assert static_mount is not None

    assets_mount = next((r for r in app.routes if getattr(r, "path", None) == "/assets"), None)
    assert assets_mount is not None
