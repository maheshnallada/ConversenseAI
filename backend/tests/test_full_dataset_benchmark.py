from pathlib import Path
import pytest
from app.storage.db import create_session_factory, init_db
from app.storage.golden_repo import GoldenDatasetRepository
from app.storage.evaluation_repo import EvaluationRepository
from app.evaluation.service import EvaluationService
from app.validation.benchmark import BenchmarkEngine

def test_full_dataset_benchmark_execution():
    root = Path(__file__).resolve().parent.parent.parent
    db_path = root / "backend" / "conversense.sqlite3"
    factory = create_session_factory(f"sqlite:///{db_path}")
    init_db(factory)

    golden_repo = GoldenDatasetRepository(factory)
    eval_service = EvaluationService(factory)
    eval_repo = EvaluationRepository(factory)

    all_labels = golden_repo.get_all()
    # Filter for standard assignment calls
    golden_labels = [l for l in all_labels if l.call_id.startswith("call_") and not l.call_id.startswith("call_test_")]
    assert len(golden_labels) == 50

    evaluations_by_call = {}
    for g in golden_labels:
        resolved_id = eval_service.resolve_interaction_id("health_campaign", g.call_id)
        evals = eval_repo.get_by_interaction("health_campaign", resolved_id)
        assert len(evals) >= 5
        evaluations_by_call[g.call_id] = evals

    engine = BenchmarkEngine()
    report = engine.evaluate_benchmark(golden_labels, evaluations_by_call)

    assert report.total_interactions == 50
    assert len(report.dimension_metrics) == 5
    assert len(report.confusion_matrices) == 5
    assert report.abstention_rate == 0.70
