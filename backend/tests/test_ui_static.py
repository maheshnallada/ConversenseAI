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

    assert "benchmark.details?.availability?.conversation_status" in source
    assert "benchmark.details?.availability?.language_slice" in source
    assert "language_slice_metrics" in source
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
