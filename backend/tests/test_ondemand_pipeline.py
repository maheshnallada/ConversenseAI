from pathlib import Path
import pytest
from app.storage.db import create_session_factory, init_db
from app.evaluation.service import EvaluationService
from app.ingestion.service import IngestionService
from app.storage.evaluation_repo import EvaluationRepository

@pytest.fixture
def db_session_factory():
    root = Path(__file__).resolve().parent.parent.parent
    db_path = root / "backend" / "conversense.sqlite3"
    factory = create_session_factory(f"sqlite:///{db_path}")
    init_db(factory)
    return factory

def test_on_demand_evaluation_existing_call(db_session_factory):
    eval_service = EvaluationService(session_factory=db_session_factory)

    # Resolves call_01 and evaluates
    results = eval_service.evaluate_interaction(tenant_id="health_campaign", interaction_id="call_01")
    assert len(results) >= 5

    families = {r.family for r in results}
    assert "compliance" in families
    assert "outcome" in families
    assert "experience" in families
    assert "quality" in families
    assert "facts" in families

    resolved_id = eval_service.resolve_interaction_id("health_campaign", "call_01")

    # Verify persisted in database
    eval_repo = EvaluationRepository(session_factory=db_session_factory)
    saved = eval_repo.get_by_interaction(tenant_id="health_campaign", interaction_id=resolved_id)
    assert len(saved) >= 5

def test_on_demand_pipeline_new_call_folder(db_session_factory):
    eval_service = EvaluationService(session_factory=db_session_factory)
    root = Path(__file__).resolve().parent.parent.parent
    call_folder = root / "data" / "calls" / "call_03"

    report = eval_service.process_and_evaluate_folder(
        call_folder_path=call_folder,
        tenant_id="health_campaign",
    )

    assert report["folder_name"] == "call_03"
    assert report["turns_count"] > 0
    assert report["timeline_reconstructed"] is True
    assert report["metrics_calculated"] is True
    assert report["evaluations_count"] >= 5
    assert "evaluations" in report

    ingestion_service = IngestionService(db_session_factory)
    assert ingestion_service.outbox_count("health_campaign", report["interaction_id"]) == 1

    eval_service.process_and_evaluate_folder(
        call_folder_path=call_folder,
        tenant_id="health_campaign",
    )
    assert ingestion_service.outbox_count("health_campaign", report["interaction_id"]) == 1
