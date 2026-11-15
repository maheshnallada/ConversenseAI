import json
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from app.domain.envelope import InteractionEnvelope
from app.domain.evaluation import EvaluationBatchRecord, EvaluationRun
from app.domain.transcript import TranscriptTurn
from app.evaluation.service import EvaluationService
from app.ingestion.post_import_processor import PostImportProcessor
from app.storage.db import create_session_factory, init_db
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


def test_golden_run_does_not_satisfy_imported_call_evaluation(
    tmp_path: Path,
    session_factory,
    monkeypatch,
):
    folder = create_call_folder(tmp_path / "golden-replay")
    _, envelope, turns, validation = imported_call(folder, [])
    repository = EvaluationRepository(session_factory)
    golden_run = make_run("completed", "golden-run")
    golden_run.evaluation_namespace = "golden"
    golden_run.batches[0].evaluation_namespace = "golden"
    repository.save_run(golden_run)
    evaluated: list[str] = []

    def evaluate(self, tenant_id, interaction_id, retry_from_run_id=None):
        evaluated.append(interaction_id)
        run = make_run("completed", "interaction-run")
        self.eval_repo.save_run(run)
        return run

    monkeypatch.setattr(EvaluationService, "evaluate_interaction", evaluate)

    result = PostImportProcessor(session_factory).process_imported_call(
        folder,
        envelope,
        turns,
        validation,
    )

    assert result.evaluation_run_id == "interaction-run"
    assert evaluated == ["processor-call"]
    assert repository.get_latest_run(
        "tenant-a",
        "processor-call",
        evaluation_namespace="golden",
    ).run_id == "golden-run"


def test_concurrent_replays_share_one_run_across_processors(
    tmp_path: Path,
    monkeypatch,
):
    database_path = tmp_path / "concurrent.sqlite"
    session_factory = create_session_factory(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    init_db(session_factory)
    folder = create_call_folder(tmp_path / "concurrent-call")
    _, envelope, turns, validation = imported_call(folder, [])
    monkeypatch.setattr(
        TimelineRepository,
        "get_timeline",
        lambda self, tenant_id, interaction_id: object(),
    )
    monkeypatch.setattr(
        ObservabilityRepository,
        "get_metrics",
        lambda self, tenant_id, interaction_id: object(),
    )
    processors = [
        PostImportProcessor(session_factory),
        PostImportProcessor(session_factory),
    ]
    calls = []
    calls_lock = threading.Lock()
    save_lock = threading.Lock()

    def evaluate(self, tenant_id, interaction_id, retry_from_run_id=None):
        with calls_lock:
            calls.append(interaction_id)
            run_id = f"concurrent-run-{len(calls)}"
        time.sleep(0.2)
        run = make_run("completed", run_id)
        with save_lock:
            self.eval_repo.save_run(run)
        return run

    monkeypatch.setattr(EvaluationService, "evaluate_interaction", evaluate)
    start = threading.Barrier(3)

    def process(processor):
        start.wait(timeout=3)
        return processor.process_imported_call(
            folder,
            envelope,
            turns,
            validation,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(process, processor) for processor in processors]
        start.wait(timeout=3)
        results = [future.result(timeout=5) for future in futures]

    assert len(calls) == 1
    assert results[0].evaluation_run_id == results[1].evaluation_run_id
    assert results[0].evaluation_status == results[1].evaluation_status == "ready"


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


def test_evaluation_guard_releases_after_failure_for_later_retry(
    tmp_path: Path,
    session_factory,
    monkeypatch,
):
    folder = create_call_folder(tmp_path / "evaluation-retry")
    _, envelope, turns, validation = imported_call(folder, [])
    attempts = 0

    def evaluate(self, tenant_id, interaction_id, retry_from_run_id=None):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("evaluation unavailable")
        run = make_run("completed", "retried-run")
        self.eval_repo.save_run(run)
        return run

    monkeypatch.setattr(EvaluationService, "evaluate_interaction", evaluate)
    processor = PostImportProcessor(session_factory)

    first_result = processor.process_imported_call(
        folder,
        envelope,
        turns,
        validation,
    )
    retry_result = processor.process_imported_call(
        folder,
        envelope,
        turns,
        validation,
    )

    assert first_result.evaluation_status == "failed"
    assert retry_result.evaluation_status == "ready"
    assert retry_result.evaluation_run_id == "retried-run"
    assert attempts == 2
