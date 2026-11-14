from pathlib import Path
import pytest
from sqlalchemy.exc import OperationalError

from app.storage.db import create_session_factory
from app.storage.golden_repo import GoldenDatasetRepository
from app.storage.evaluation_repo import EvaluationRepository
from app.domain.golden import GoldenCallLabel
from app.evaluation.service import EvaluationService
from app.storage.orm import GoldenCallLabelRow
from app.validation.benchmark import BenchmarkEngine

def test_full_dataset_benchmark_execution():
    root = Path(__file__).resolve().parent.parent.parent
    db_path = root / "backend" / "conversense.sqlite3"
    if not db_path.is_file():
        pytest.skip(f"external benchmark database is unavailable: {db_path}")

    factory = create_session_factory(f"sqlite:///{db_path}")
    golden_repo = GoldenDatasetRepository(factory)
    eval_service = EvaluationService(factory)
    eval_repo = EvaluationRepository(factory)

    try:
        all_labels = golden_repo.get_all()
    except OperationalError as exc:
        pytest.skip(f"external benchmark database schema is unavailable: {exc}")

    # Filter for standard assignment calls
    golden_labels = [l for l in all_labels if l.call_id.startswith("call_") and not l.call_id.startswith("call_test_")]
    if len(golden_labels) != 50:
        pytest.skip(
            f"external benchmark database contains {len(golden_labels)} standard labels; expected 50"
        )

    evaluations_by_call = {}
    try:
        for g in golden_labels:
            resolved_id = eval_service.resolve_interaction_id("health_campaign", g.call_id)
            evals = eval_repo.get_by_interaction("health_campaign", resolved_id)
            if len(evals) < 5:
                pytest.skip(
                    f"precomputed evaluations are unavailable for {g.call_id}: found {len(evals)}, expected at least 5"
                )
            evaluations_by_call[g.call_id] = evals
    except OperationalError as exc:
        pytest.skip(f"external benchmark schema is unavailable: {exc}")

    engine = BenchmarkEngine()
    report = engine.evaluate_benchmark(golden_labels, evaluations_by_call)

    assert report.total_interactions == 50
    assert len(report.dimension_metrics) == 5
    assert len(report.confusion_matrices) == 5
    assert report.abstention_rate == 0.70


def test_full_dataset_benchmark_skips_when_interaction_table_is_missing(
    tmp_path, monkeypatch
):
    repository_root = tmp_path / "repository"
    test_file = repository_root / "backend" / "tests" / "test_full_dataset_benchmark.py"
    db_path = repository_root / "backend" / "conversense.sqlite3"
    db_path.parent.mkdir(parents=True)
    monkeypatch.setitem(globals(), "__file__", str(test_file))

    factory = create_session_factory(f"sqlite:///{db_path}")
    GoldenCallLabelRow.__table__.create(factory.engine)
    GoldenDatasetRepository(factory).save_many(
        [
            GoldenCallLabel(
                call_id=f"call_{index:02d}",
                what_happened="Test call",
                correct_outcome="Unknown",
            )
            for index in range(50)
        ]
    )

    with pytest.raises(pytest.skip.Exception, match="schema is unavailable"):
        test_full_dataset_benchmark_execution()
