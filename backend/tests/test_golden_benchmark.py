import asyncio
import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.domain.evaluation import EvaluationBatchRecord, EvaluationRun
from app.evaluation.service import EvaluationService
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.golden_repo import GoldenDatasetRepository
from app.storage.orm import InteractionRow
from app.validation.golden_benchmark import GoldenDatasetBenchmarkService


TENANT_ID = "tenant_golden_benchmark"
HEADERS = [
    "call_id",
    "model_input_json_excluding_saved_outcome",
    "gold_correct_outcome",
    "gold_sentiment",
    "gold_emotion",
    "gold_overall",
    "gold_never-rule_broken",
    "gold_test_flag",
    "source_call_json",
    "call_log",
    "gold_observability_notes",
    "conversation_status",
    "language_slice",
]


def _record(call_id: str, message: str = "hello", **overrides) -> dict[str, str]:
    row = {
        "call_id": call_id,
        "model_input_json_excluding_saved_outcome": json.dumps(
            {
                "call_id": call_id,
                "started_at": "2026-01-01T00:00:00+00:00",
                "ended_at": "2026-01-01T00:01:00+00:00",
                "end_reason": "ended",
                "channel": "phone",
                "environment": "staging",
                "meta": {"campaign_id": "benchmark-test"},
                "messages": [
                    {"role": "assistant", "content": message, "t": 0.0},
                    {"role": "user", "content": "yes", "t": 1.0},
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
    row.update(overrides)
    return row


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def _write_duplicate_header_csv(path):
    path.write_text(
        "call_id,model_input_json_excluding_saved_outcome,"
        "gold_correct_outcome,gold_correct_outcome,gold_sentiment,"
        "gold_emotion,gold_overall,gold_never-rule_broken\n"
        "call_duplicate,not-json,Expected,Corrupted,Neutral,Neutral,Good,None\n",
        encoding="utf-8",
    )


def _batch(call_id, batch_name, status, output):
    now = datetime.now(timezone.utc)
    return EvaluationBatchRecord(
        evaluation_id=f"{call_id}-{batch_name}-{uuid4()}",
        batch_name=batch_name,
        status=status,
        model="test-model",
        prompt_version="1",
        schema_version="1",
        started_at=now,
        completed_at=now,
        input_tokens=1,
        output_tokens=1,
        raw_output="{}" if status == "completed" else None,
        parsed_output=output,
        validation={
            "schema_valid": status == "completed",
            "evidence_valid": status == "completed",
        },
        review_required=status != "completed",
        review_status="required" if status != "completed" else "not_required",
        review_reasons=[],
    )


class _RecordingEvaluationService:
    def __init__(self, session_factory, failed_call_ids=()):
        self.repo = EvaluationRepository(session_factory)
        self.failed_call_ids = set(failed_call_ids)
        self.calls = []
        self.active = 0
        self.max_active = 0

    async def evaluate_input(self, interaction, turns, evaluation_namespace):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.005)
            self.calls.append((interaction, turns, evaluation_namespace))
            failed = interaction.interaction_id in self.failed_call_ids
            understanding = {
                "outcome": {"label": "Not interested"},
                "sentiment": {"label": "Neutral"},
                "emotion": {"label": "Neutral"},
            }
            batches = [
                _batch(
                    interaction.interaction_id,
                    "conversation_understanding",
                    "failed" if failed else "completed",
                    None if failed else understanding,
                ),
                _batch(
                    interaction.interaction_id,
                    "conversation_quality",
                    "completed",
                    {"conversation_completeness": {"conversation_status": "COMPLETED"}},
                ),
                _batch(
                    interaction.interaction_id,
                    "compliance_appointment",
                    "completed",
                    {"compliance": {"rule_results": {}}},
                ),
            ]
            now = datetime.now(timezone.utc)
            run = EvaluationRun(
                run_id=f"run-{interaction.interaction_id}-{uuid4()}",
                tenant_id=interaction.tenant_id,
                interaction_id=interaction.interaction_id,
                batches=batches,
                summary={"overall_assessment": "Good"},
                started_at=now,
                completed_at=now,
                review_required=failed,
                review_reasons=[],
                evaluation_namespace=evaluation_namespace,
            )
            for batch in run.batches:
                batch.evaluation_namespace = evaluation_namespace
            self.repo.save_run(run)
            return run
        finally:
            self.active -= 1


def _service(session_factory, monkeypatch, **evaluation_options):
    evaluation_service = _RecordingEvaluationService(
        session_factory, **evaluation_options
    )
    monkeypatch.setattr(
        "app.validation.golden_benchmark.EvaluationService",
        lambda _: evaluation_service,
    )
    return (
        GoldenDatasetBenchmarkService(session_factory),
        evaluation_service,
    )


def test_import_evaluates_csv_only_record_and_benchmarks_without_interaction_row(
    session_factory, tmp_path, monkeypatch
):
    csv_path = tmp_path / "golden.csv"
    _write_csv(
        csv_path,
        [
            _record(
                "call_csv_only",
                source_call_json='{"saved_outcome":"must not be evaluated"}',
                call_log="must not be evaluated",
                gold_observability_notes="must not be evaluated",
            )
        ],
    )
    service, evaluation_service = _service(session_factory, monkeypatch)

    result = service.import_and_benchmark(csv_path, TENANT_ID)

    assert result.records_seen == 1
    assert result.labels_imported == 1
    assert result.evaluations_created == 1
    assert result.evaluations_reused == 0
    assert result.records[0].evaluation_status == "ready"
    assert result.records[0].evaluation_run_id
    interaction, turns, namespace = evaluation_service.calls[0]
    assert interaction.interaction_id == "call_csv_only"
    assert turns
    assert namespace.startswith("golden_dataset:")
    evaluation_context = interaction.model_dump_json() + json.dumps(
        [asdict(turn) for turn in turns]
    )
    assert "must not be evaluated" not in evaluation_context
    assert "gold_correct_outcome" not in evaluation_context
    with session_factory() as session:
        assert session.scalar(
            select(InteractionRow).where(
                InteractionRow.tenant_id == TENANT_ID,
                InteractionRow.interaction_id == "call_csv_only",
            )
        ) is None
    assert result.report.total_interactions == 1
    assert (
        result.report.confusion_matrices["correct_outcome"].matrix["Not interested"][
            "Not interested"
        ]
        == 1
    )


def test_identical_input_reuses_run_after_label_only_edit(
    session_factory, tmp_path, monkeypatch
):
    csv_path = tmp_path / "golden.csv"
    row = _record("call_reused")
    _write_csv(csv_path, [row])
    service, evaluation_service = _service(session_factory, monkeypatch)

    first = service.import_and_benchmark(csv_path, TENANT_ID)
    row["gold_correct_outcome"] = "Expert call booked"
    _write_csv(csv_path, [row])
    second = service.import_and_benchmark(csv_path, TENANT_ID)

    assert first.dataset_hash != second.dataset_hash
    assert first.records[0].evaluation_run_id == second.records[0].evaluation_run_id
    assert first.records[0].reused is False
    assert second.records[0].reused is True
    assert second.evaluations_created == 0
    assert second.evaluations_reused == 1
    assert len(evaluation_service.calls) == 1
    saved_label = GoldenDatasetRepository(session_factory).get_by_call_id(
        "call_reused"
    )
    assert saved_label.correct_outcome == "Expert call booked"


def test_changed_input_uses_new_golden_namespace_without_touching_normal_run(
    session_factory, tmp_path, monkeypatch
):
    csv_path = tmp_path / "golden.csv"
    _write_csv(csv_path, [_record("call_namespace")])
    service, evaluation_service = _service(session_factory, monkeypatch)
    normal_repo = EvaluationRepository(session_factory)
    now = datetime.now(timezone.utc)
    normal_run = EvaluationRun(
        run_id="normal-run",
        tenant_id=TENANT_ID,
        interaction_id="call_namespace",
        batches=[
            _batch("call_namespace", "conversation_understanding", "completed", {})
        ],
        summary={"overall_assessment": "Bad"},
        started_at=now,
        completed_at=now,
        review_required=False,
        review_reasons=[],
        evaluation_namespace="interaction",
    )
    for batch in normal_run.batches:
        batch.evaluation_namespace = "interaction"
    normal_repo.save_run(normal_run)

    first = service.import_and_benchmark(csv_path, TENANT_ID)
    _write_csv(csv_path, [_record("call_namespace", message="different input")])
    second = service.import_and_benchmark(csv_path, TENANT_ID)

    assert first.records[0].evaluation_run_id != second.records[0].evaluation_run_id
    assert evaluation_service.calls[0][2] != evaluation_service.calls[1][2]
    assert evaluation_service.calls[0][2].startswith("golden_dataset:")
    assert evaluation_service.calls[1][2].startswith("golden_dataset:")
    assert (
        normal_repo.get_latest_run(TENANT_ID, "call_namespace").run_id
        == "normal-run"
    )
    assert len(evaluation_service.calls) == 2


def test_failed_eligible_records_are_counted_and_benchmarked_as_abstentions(
    session_factory, tmp_path, monkeypatch
):
    csv_path = tmp_path / "golden.csv"
    invalid = _record(
        "call_invalid_json",
        model_input_json_excluding_saved_outcome="{not-json",
    )
    _write_csv(csv_path, [invalid, _record("call_failed_evaluation")])
    service, evaluation_service = _service(
        session_factory, monkeypatch, failed_call_ids={"call_failed_evaluation"}
    )

    result = service.import_and_benchmark(csv_path, TENANT_ID)
    repeated = service.import_and_benchmark(csv_path, TENANT_ID)

    assert result.labels_imported == 2
    assert result.evaluations_failed == 2
    assert result.evaluations_created == 1
    assert result.report.total_interactions == 2
    assert result.records[0].evaluation_status == "failed"
    assert result.records[1].evaluation_status == "failed"
    assert result.records[0].evaluation_run_id is None
    assert result.records[0].error
    assert "not-json" not in result.records[0].error
    assert len(evaluation_service.calls) == 1
    assert repeated.evaluations_reused == 1
    assert repeated.evaluations_failed == 2
    assert repeated.records[1].reused is True
    assert repeated.records[1].evaluation_status == "failed"
    assert (
        result.report.confusion_matrices["correct_outcome"].matrix["Not interested"][
            "Can't tell"
        ]
        == 2
    )


def test_import_excludes_only_true_flags_and_limits_concurrent_records(
    session_factory, tmp_path, monkeypatch
):
    csv_path = tmp_path / "golden.csv"
    rows = [
        _record("call_false", gold_test_flag="False"),
        _record("call_unknown", gold_test_flag="Unknown"),
        _record("call_true", gold_test_flag="True"),
        _record("call_unset", gold_test_flag=""),
        _record("call_fifth", gold_test_flag="False"),
    ]
    _write_csv(csv_path, rows)
    service, evaluation_service = _service(session_factory, monkeypatch)

    result = service.import_and_benchmark(csv_path, TENANT_ID)

    assert result.records_seen == 5
    assert result.labels_imported == 5
    assert result.test_records_excluded == 1
    assert result.report.total_interactions == 4
    assert result.records[2].evaluation_status == "excluded"
    assert result.evaluations_created == 4
    assert evaluation_service.max_active <= 2


def test_get_benchmark_reads_current_rows_without_saving_or_evaluating(
    session_factory, tmp_path, monkeypatch
):
    csv_path = tmp_path / "golden.csv"
    _write_csv(csv_path, [_record("call_read_only")])
    service, evaluation_service = _service(session_factory, monkeypatch)

    report = service.get_benchmark(csv_path, TENANT_ID)

    assert report.total_interactions == 1
    assert evaluation_service.calls == []
    assert GoldenDatasetRepository(session_factory).get_all() == []


def test_report_does_not_score_optional_reference_columns(
    session_factory, tmp_path, monkeypatch
):
    csv_path = tmp_path / "golden.csv"
    _write_csv(
        csv_path,
        [
            _record(
                "call_reference_columns",
                conversation_status="COMPLETED",
                language_slice="reference-only",
            )
        ],
    )
    service, _ = _service(session_factory, monkeypatch)

    report = service.import_and_benchmark(csv_path, TENANT_ID).report

    assert "conversation_status" not in report.dimension_metrics
    assert "conversation_status" not in report.confusion_matrices
    assert "language_slice_metrics" not in report.details


def test_import_rejects_duplicate_headers_before_persisting_labels(
    session_factory, tmp_path
):
    csv_path = tmp_path / "duplicate_headers.csv"
    _write_duplicate_header_csv(csv_path)

    with pytest.raises(ValueError, match="Duplicate CSV header"):
        GoldenDatasetBenchmarkService(session_factory).import_and_benchmark(
            csv_path, TENANT_ID
        )

    assert (
        GoldenDatasetRepository(session_factory).get_by_call_id("call_duplicate")
        is None
    )
