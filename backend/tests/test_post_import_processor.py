import json
import wave
from datetime import datetime, timezone
from pathlib import Path

from app.domain.envelope import InteractionEnvelope
from app.domain.evaluation import EvaluationBatchRecord, EvaluationRun
from app.domain.transcript import TranscriptTurn
from app.evaluation.service import EvaluationService
from app.ingestion.post_import_processor import PostImportProcessor
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.observability_repo import ObservabilityRepository
from app.storage.timeline_repo import TimelineRepository
from app.validation.audio import validate_call_files


def create_call_folder(folder: Path, messages: list[dict] | None = None) -> Path:
    folder.mkdir(parents=True)
    (folder / "call.json").write_text(
        json.dumps(
            {
                "call_id": "processor-call",
                "meta": {"connected_s": 1.0},
                "messages": messages or [],
            }
        ),
        encoding="utf-8",
    )
    with wave.open(str(folder / "recording.wav"), "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        recording.writeframes(b"\x01\x00" * 1600)
    return folder


def imported_call(folder: Path, turns: list[TranscriptTurn]):
    return (
        folder,
        InteractionEnvelope(
            tenant_id="tenant-a",
            interaction_id="processor-call",
            schema_version="1.0",
            domain_data={"meta": {"connected_s": 1.0}},
        ),
        turns,
        validate_call_files(folder),
    )


def make_run(
    status: str = "completed",
    run_id: str = "processor-run",
) -> EvaluationRun:
    now = datetime.now(timezone.utc)
    batches = [
        EvaluationBatchRecord(
            evaluation_id=f"{run_id}-batch",
            batch_name="sample",
            status=status,
            model="test-model",
            prompt_version="1",
            schema_version="1",
            started_at=now,
            completed_at=now,
            input_tokens=None,
            output_tokens=None,
            raw_output=None,
            parsed_output=None,
            validation={},
            review_required=False,
            review_status="NOT_REQUIRED",
            review_reasons=[],
        )
    ]
    return EvaluationRun(
        run_id=run_id,
        tenant_id="tenant-a",
        interaction_id="processor-call",
        batches=batches,
        summary={},
        started_at=now,
        completed_at=now,
        review_required=False,
        review_reasons=[],
    )


def test_process_imported_call_persists_timeline_metrics_and_evaluation(
    tmp_path: Path,
    session_factory,
    monkeypatch,
):
    folder = create_call_folder(tmp_path / "call")
    _, envelope, turns, validation = imported_call(
        folder,
        [
            TranscriptTurn(
                turn_id="turn-0",
                interaction_id="processor-call",
                tenant_id="tenant-a",
                turn_index=0,
                speaker="agent",
                raw_text="Hello",
                normalized_text="Hello",
                start_s=0.0,
                end_s=0.5,
                duration_s=0.5,
            )
        ],
    )
    evaluated: list[tuple[str, str, str | None]] = []

    def evaluate(self, tenant_id, interaction_id, retry_from_run_id=None):
        evaluated.append((tenant_id, interaction_id, retry_from_run_id))
        run = make_run()
        self.eval_repo.save_run(run)
        return run

    monkeypatch.setattr(EvaluationService, "evaluate_interaction", evaluate)
    processor = PostImportProcessor(session_factory)

    result = processor.process_imported_call(folder, envelope, turns, validation)

    assert result.transcript_turns == 1
    assert result.timeline_status == "ready"
    assert result.observability_status == "ready"
    assert result.evaluation_status == "ready"
    assert result.evaluation_run_id == "processor-run"
    assert result.errors == []
    assert TimelineRepository(session_factory).get_timeline(
        "tenant-a", "processor-call"
    ).events[0].text == "Hello"
    assert ObservabilityRepository(session_factory).get_metrics(
        "tenant-a", "processor-call"
    ).turn_count == 1
    assert evaluated == [("tenant-a", "processor-call", None)]


def test_replay_fills_missing_outputs_without_duplicating_existing_evaluation(
    tmp_path: Path,
    session_factory,
    monkeypatch,
):
    folder = create_call_folder(tmp_path / "replay")
    _, envelope, turns, validation = imported_call(folder, [])
    EvaluationRepository(session_factory).save_run(make_run("completed", "existing-run"))
    calls: list[str] = []

    def should_not_evaluate(self, tenant_id, interaction_id, retry_from_run_id=None):
        calls.append(interaction_id)
        raise AssertionError("an existing evaluation run must not be duplicated")

    monkeypatch.setattr(
        EvaluationService,
        "evaluate_interaction",
        should_not_evaluate,
    )

    result = PostImportProcessor(session_factory).process_imported_call(
        folder,
        envelope,
        turns,
        validation,
    )

    assert result.transcript_turns == 0
    assert result.timeline_status == "ready"
    assert result.observability_status == "ready"
    assert result.evaluation_status == "ready"
    assert result.evaluation_run_id == "existing-run"
    assert result.errors == []
    assert TimelineRepository(session_factory).get_timeline(
        "tenant-a", "processor-call"
    ) is not None
    assert ObservabilityRepository(session_factory).get_metrics(
        "tenant-a", "processor-call"
    ) is not None
    assert calls == []


def test_failed_evaluation_batch_returns_failed_status_and_run_id(
    tmp_path: Path,
    session_factory,
    monkeypatch,
):
    folder = create_call_folder(tmp_path / "failed-evaluation")
    _, envelope, turns, validation = imported_call(folder, [])

    def evaluate(self, tenant_id, interaction_id, retry_from_run_id=None):
        run = make_run("failed", "failed-run")
        self.eval_repo.save_run(run)
        return run

    monkeypatch.setattr(EvaluationService, "evaluate_interaction", evaluate)

    result = PostImportProcessor(session_factory).process_imported_call(
        folder,
        envelope,
        turns,
        validation,
    )

    assert result.evaluation_status == "failed"
    assert result.evaluation_run_id == "failed-run"
    assert [error.stage for error in result.errors] == ["evaluation"]


def test_timeline_failure_does_not_stop_observability_or_evaluation(
    tmp_path: Path,
    session_factory,
    monkeypatch,
):
    folder = create_call_folder(tmp_path / "timeline-error")
    _, envelope, turns, validation = imported_call(folder, [])

    def fail_timeline(self, timeline):
        raise OSError(f"failed at {folder}")

    def evaluate(self, tenant_id, interaction_id, retry_from_run_id=None):
        run = make_run()
        self.eval_repo.save_run(run)
        return run

    monkeypatch.setattr(TimelineRepository, "save_timeline", fail_timeline)
    monkeypatch.setattr(EvaluationService, "evaluate_interaction", evaluate)

    result = PostImportProcessor(session_factory).process_imported_call(
        folder,
        envelope,
        turns,
        validation,
    )

    assert result.timeline_status == "failed"
    assert result.observability_status == "ready"
    assert result.evaluation_status == "ready"
    assert result.evaluation_run_id == "processor-run"
    assert [error.stage for error in result.errors] == ["timeline"]
    assert str(folder) not in result.errors[0].message
    assert ObservabilityRepository(session_factory).get_metrics(
        "tenant-a", "processor-call"
    ) is not None


def test_zero_turn_call_has_explicit_ready_statuses(
    tmp_path: Path,
    session_factory,
    monkeypatch,
):
    folder = create_call_folder(tmp_path / "empty")
    _, envelope, turns, validation = imported_call(folder, [])

    def evaluate(self, tenant_id, interaction_id, retry_from_run_id=None):
        run = make_run()
        self.eval_repo.save_run(run)
        return run

    monkeypatch.setattr(EvaluationService, "evaluate_interaction", evaluate)

    result = PostImportProcessor(session_factory).process_imported_call(
        folder,
        envelope,
        turns,
        validation,
    )

    assert result.transcript_turns == 0
    assert result.timeline_status == "ready"
    assert result.observability_status == "ready"
    assert result.evaluation_status == "ready"


def test_evaluation_exception_is_reported_without_exposing_folder_path(
    tmp_path: Path,
    session_factory,
    monkeypatch,
):
    folder = create_call_folder(tmp_path / "evaluation-error")
    _, envelope, turns, validation = imported_call(folder, [])

    def fail_evaluation(self, tenant_id, interaction_id, retry_from_run_id=None):
        raise RuntimeError(f"failed at {folder}")

    monkeypatch.setattr(
        EvaluationService,
        "evaluate_interaction",
        fail_evaluation,
    )

    result = PostImportProcessor(session_factory).process_imported_call(
        folder,
        envelope,
        turns,
        validation,
    )

    assert result.timeline_status == "ready"
    assert result.observability_status == "ready"
    assert result.evaluation_status == "failed"
    assert result.evaluation_run_id is None
    assert [error.stage for error in result.errors] == ["evaluation"]
    assert str(folder) not in result.errors[0].message
