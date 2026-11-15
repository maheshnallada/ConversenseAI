import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.domain.benchmark import BenchmarkReport
from app.domain.evaluation import EvaluationBatchRecord, EvaluationRun
from app.domain.golden import GoldenCallLabel, GoldenDataset, GoldenDatasetRecord
from scripts import validate_golden_dataset


def _outcome_run(call_id: str, outcome: str) -> EvaluationRun:
    now = datetime.now(timezone.utc)
    batch = EvaluationBatchRecord(
        evaluation_id=f"batch-{call_id}",
        batch_name="conversation_understanding",
        status="completed",
        model="test-model",
        prompt_version="1",
        schema_version="1",
        started_at=now,
        completed_at=now,
        input_tokens=1,
        output_tokens=1,
        raw_output="{}",
        parsed_output={"outcome": {"label": outcome}},
        validation={"schema_valid": True, "evidence_valid": True},
        review_required=False,
        review_status="not_required",
        review_reasons=[],
    )
    return EvaluationRun(
        run_id=f"run-{call_id}",
        tenant_id="tenant",
        interaction_id=call_id,
        batches=[batch],
        summary={"overall_assessment": "Good"},
        started_at=now,
        completed_at=now,
        review_required=False,
        review_reasons=[],
    )


def test_report_reconciliations_reflect_actual_predictions(tmp_path: Path) -> None:
    labels = [
        GoldenCallLabel(
            call_id="call_01",
            what_happened="Call reached an ending",
            correct_outcome="Not interested",
        ),
        GoldenCallLabel(
            call_id="call_02",
            what_happened="Call reached an ending",
            correct_outcome="Voicemail",
        ),
    ]
    evaluations = {"call_01": _outcome_run("call_01", "Expert call booked")}
    report_path = tmp_path / "report.md"

    try:
        rows = validate_golden_dataset.build_reconciliation_rows(labels, evaluations)
        validate_golden_dataset.generate_markdown_report(
            BenchmarkReport(total_interactions=2),
            report_path,
            rows,
        )
    except (AttributeError, TypeError) as exc:
        pytest.fail(f"report generation must accept and derive reconciliation data: {exc}")

    report_text = report_path.read_text(encoding="utf-8")
    assert "`call_01`" in report_text
    assert "Ground truth `Not interested`" in report_text
    assert "prediction `Expert call booked`" in report_text
    assert "Does not match ground truth" in report_text
    assert "Ground truth `Voicemail`" in report_text
    assert "prediction `Can't tell`" in report_text


def test_main_reads_dataset_and_benchmark_namespace_without_importing_labels(
    tmp_path: Path, monkeypatch
) -> None:
    repository_root = tmp_path / "repository"
    script_path = repository_root / "scripts" / "validate_golden_dataset.py"
    script_path.parent.mkdir(parents=True)
    report_path = repository_root / "docs" / "GOLDEN_DATASET_BENCHMARK.md"
    monkeypatch.setattr(
        validate_golden_dataset,
        "__file__",
        str(script_path),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_golden_dataset", "--db-url", "sqlite:///test.db"],
    )
    monkeypatch.setattr(validate_golden_dataset, "create_session_factory", lambda _url: object())
    monkeypatch.setattr(validate_golden_dataset, "init_db", lambda _factory: None)
    label = GoldenCallLabel(
        call_id="call_01",
        what_happened="Call reached an ending",
        correct_outcome="Expert call booked",
    )
    dataset = GoldenDataset(
        dataset_hash="dataset-hash",
        records=[GoldenDatasetRecord(label=label, input_hash="input-hash")],
    )
    loaded_paths = []

    def load_dataset(path, tenant_id):
        loaded_paths.append((path, tenant_id))
        return dataset

    class NoImplicitLabelImport:
        def __init__(self, _factory):
            pytest.fail("the report utility must not import or persist labels")

    namespace_queries = []

    class BenchmarkRuns:
        def __init__(self, _factory):
            pass

        def get_latest_run(self, tenant_id, interaction_id, evaluation_namespace):
            namespace_queries.append((tenant_id, interaction_id, evaluation_namespace))
            return _outcome_run(interaction_id, "Expert call booked")

    monkeypatch.setattr(validate_golden_dataset, "load_golden_dataset", load_dataset)
    monkeypatch.setattr(
        validate_golden_dataset,
        "GoldenDatasetRepository",
        NoImplicitLabelImport,
        raising=False,
    )
    monkeypatch.setattr(validate_golden_dataset, "EvaluationRepository", BenchmarkRuns)

    validate_golden_dataset.main()

    expected_csv = repository_root / "Conversense_AI_25_Records_Input_and_Golden.csv"
    assert loaded_paths == [(expected_csv, "health_campaign")]
    assert namespace_queries == [
        ("health_campaign", "call_01", "golden_dataset:input-hash")
    ]
    assert report_path.is_file()
    assert "prediction `Expert call booked`" in report_path.read_text(encoding="utf-8")
