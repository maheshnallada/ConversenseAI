import csv
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.domain.evaluation import EvaluationBatchRecord, EvaluationRun
from app.storage.db import create_session_factory, init_db
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.golden_repo import GoldenDatasetRepository
from app.storage.orm import EvaluationRunRow
from app.validation.golden_loader import load_golden_dataset

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import validate_golden_dataset


DATASET_FILENAME = "Conversense_AI_25_Records_Input_and_Golden.csv"


def _write_supplied_dataset(path: Path) -> None:
    fields = [
        "call_id",
        "model_input_json_excluding_saved_outcome",
        "gold_correct_outcome",
        "gold_sentiment",
        "gold_emotion",
        "gold_overall",
        "gold_never-rule_broken",
        "gold_test_flag",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for index in range(25):
            call_id = f"call_{index:02d}"
            writer.writerow(
                {
                    "call_id": call_id,
                    "model_input_json_excluding_saved_outcome": json.dumps(
                        {
                            "call_id": call_id,
                            "started_at": "2026-01-01T00:00:00+00:00",
                            "ended_at": "2026-01-01T00:01:00+00:00",
                            "end_reason": "ended",
                            "channel": "phone",
                            "environment": "staging",
                            "messages": [
                                {"role": "assistant", "content": "Hello", "t": 0.0},
                                {"role": "user", "content": "No, thanks", "t": 1.0},
                            ],
                        }
                    ),
                    "gold_correct_outcome": "Not interested",
                    "gold_sentiment": "Neutral",
                    "gold_emotion": "Neutral",
                    "gold_overall": "Good",
                    "gold_never-rule_broken": "None",
                    "gold_test_flag": "False",
                }
            )


def _save_run(repo, call_id, evaluation_namespace, outcome):
    now = datetime.now(timezone.utc)
    batch = EvaluationBatchRecord(
        evaluation_id=f"batch-{call_id}-{evaluation_namespace}",
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
        evaluation_namespace=evaluation_namespace,
    )
    repo.save_run(
        EvaluationRun(
            run_id=f"run-{call_id}-{evaluation_namespace}",
            tenant_id="health_campaign",
            interaction_id=call_id,
            batches=[batch],
            summary={"overall_assessment": "Good"},
            started_at=now,
            completed_at=now,
            review_required=False,
            review_reasons=[],
            evaluation_namespace=evaluation_namespace,
        )
    )


def test_full_dataset_benchmark_reads_supplied_dataset_and_scoped_runs(
    tmp_path, monkeypatch, capsys
):
    repository_root = tmp_path / "repository"
    scripts = repository_root / "scripts"
    scripts.mkdir(parents=True)
    csv_path = repository_root / DATASET_FILENAME
    _write_supplied_dataset(csv_path)

    db_path = tmp_path / "benchmark.sqlite3"
    factory = create_session_factory(f"sqlite:///{db_path}")
    init_db(factory)
    dataset = load_golden_dataset(csv_path, tenant_id="health_campaign")
    eval_repo = EvaluationRepository(factory)
    for record in dataset.records:
        namespace = f"golden_dataset:{record.input_hash}"
        _save_run(eval_repo, record.label.call_id, namespace, "Not interested")
        if record.label.call_id == "call_00":
            _save_run(eval_repo, record.label.call_id, "interaction", "Wrong result")

    monkeypatch.setattr(
        validate_golden_dataset, "__file__", str(scripts / "validate_golden_dataset.py")
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "validate_golden_dataset",
            "--tenant-id",
            "health_campaign",
            "--db-url",
            f"sqlite:///{db_path}",
        ],
    )

    validate_golden_dataset.main()

    report_path = repository_root / "docs" / "GOLDEN_DATASET_BENCHMARK.md"
    report_text = report_path.read_text(encoding="utf-8")
    assert "Golden interactions: 25" in capsys.readouterr().out
    assert "prediction `Not interested` (Matches ground truth)" in report_text
    assert "prediction `Wrong result`" not in report_text
    assert GoldenDatasetRepository(factory).get_all() == []
    with factory() as session:
        assert session.scalar(select(EvaluationRunRow).where(
            EvaluationRunRow.evaluation_namespace == "interaction"
        )) is not None
