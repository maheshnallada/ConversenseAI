import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.benchmark import BenchmarkReport
from app.domain.evaluation import EvaluationResult
from app.domain.golden import GoldenCallLabel
from scripts import validate_golden_dataset


def _outcome_evaluation(call_id: str, outcome: str) -> EvaluationResult:
    return EvaluationResult(
        tenant_id="tenant",
        interaction_id=call_id,
        evaluator_id="outcome",
        evaluator_version="1",
        family="outcome",
        method="deterministic",
        label=None,
        details={"correct_outcome": outcome},
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
    evaluations = {"call_01": [_outcome_evaluation("call_01", "Expert call booked")]}
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


def test_main_creates_report_parent_directory(tmp_path: Path, monkeypatch) -> None:
    report_path = tmp_path / "docs" / "PHASE_7_VALIDATION_BENCHMARK.md"
    monkeypatch.setattr(
        validate_golden_dataset,
        "__file__",
        str(tmp_path / "scripts" / "validate_golden_dataset.py"),
    )
    monkeypatch.setattr(sys, "argv", ["validate_golden_dataset"])
    monkeypatch.setattr(validate_golden_dataset, "create_session_factory", lambda _url: object())
    monkeypatch.setattr(validate_golden_dataset, "init_db", lambda _factory: None)
    monkeypatch.setattr(validate_golden_dataset, "load_golden_dataset", lambda _path: [])
    monkeypatch.setattr(validate_golden_dataset, "load_reply_wait_checks", lambda _path: [])
    monkeypatch.setattr(
        validate_golden_dataset,
        "GoldenDatasetRepository",
        lambda _factory: SimpleNamespace(save_many=lambda _labels: None),
    )
    monkeypatch.setattr(
        validate_golden_dataset,
        "EvaluationService",
        lambda _factory: SimpleNamespace(),
    )
    monkeypatch.setattr(
        validate_golden_dataset,
        "EvaluationRepository",
        lambda _factory: SimpleNamespace(),
    )

    try:
        validate_golden_dataset.main()
    except FileNotFoundError as exc:
        pytest.fail(f"main must create the report directory before writing: {exc}")

    assert report_path.is_file()
