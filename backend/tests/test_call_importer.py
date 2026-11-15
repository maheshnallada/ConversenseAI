import json
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import event, func, select

from app.evaluation.service import EvaluationService
from app.ingestion.call_importer import CallFolderImporter
from app.ingestion.post_import_processor import (
    CallProcessingError,
    CallProcessingSummary,
)
from app.storage.artifacts import LocalArtifactStore
from app.storage.orm import (
    ArtifactRow,
    InteractionRow,
    InteractionTimelineRow,
    ObservabilityMetricsRow,
    OutboxRow,
    TurnRow,
)


class ReadyProcessor:
    def __init__(self) -> None:
        self.calls = []

    def process_imported_call(self, folder_path, envelope, turns, validation):
        self.calls.append(envelope.interaction_id)
        return CallProcessingSummary(
            transcript_turns=len(turns),
            timeline_status="ready",
            observability_status="ready",
            evaluation_status="ready",
            evaluation_run_id=f"run-{envelope.interaction_id}",
            errors=[],
        )


def create_call_folder(
    folder: Path,
    call_id: str = "import-call",
    message: str = "Hello",
) -> Path:
    folder.mkdir(parents=True)
    (folder / "call.json").write_text(
        json.dumps(
            {
                "call_id": call_id,
                "messages": [
                    {"role": "assistant", "content": message, "t": 0.0},
                ],
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


def row_count(session_factory, model):
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(model))


def test_import_call_persists_interaction_transcript_and_artifacts(
    tmp_path: Path,
    session_factory,
    monkeypatch,
):
    folder = create_call_folder(tmp_path / "call")
    store = LocalArtifactStore(tmp_path / "artifacts")
    evaluated = []

    def evaluate(self, tenant_id, interaction_id, retry_from_run_id=None):
        evaluated.append((tenant_id, interaction_id, retry_from_run_id))
        return SimpleNamespace(run_id="import-run", batches=[])

    monkeypatch.setattr(EvaluationService, "evaluate_interaction", evaluate)
    importer = CallFolderImporter(session_factory, store)

    result = importer.import_call(folder, "tenant-a")

    assert result.status == "created"
    assert result.interaction_id == "import-call"
    assert result.folder_name == "call"
    assert result.files_count == 2
    assert result.audio_validation.is_valid is True
    assert result.audio_validation.channels == 1
    assert result.processing.timeline_status == "ready"
    assert result.processing.observability_status == "ready"
    assert result.processing.evaluation_run_id == "import-run"
    assert row_count(session_factory, InteractionTimelineRow) == 1
    assert row_count(session_factory, ObservabilityMetricsRow) == 1
    assert evaluated == [("tenant-a", "import-call", None)]
    assert row_count(session_factory, InteractionRow) == 1
    assert row_count(session_factory, OutboxRow) == 1
    assert row_count(session_factory, TurnRow) == 1
    assert row_count(session_factory, ArtifactRow) == 2


def test_import_call_exact_replay_does_not_duplicate_rows(
    tmp_path: Path,
    session_factory,
):
    folder = create_call_folder(tmp_path / "call")
    renamed_folder = create_call_folder(tmp_path / "renamed", message="Hello")
    processor = ReadyProcessor()
    importer = CallFolderImporter(
        session_factory,
        LocalArtifactStore(tmp_path / "artifacts"),
        processor,
    )

    first = importer.import_call(folder, "tenant-a")
    replay = importer.import_call(renamed_folder, "tenant-a")

    assert first.status == "created"
    assert replay.status == "replayed"
    assert first.processing is not None
    assert replay.processing is not None
    assert processor.calls == ["import-call", "import-call"]
    assert row_count(session_factory, InteractionRow) == 1
    assert row_count(session_factory, OutboxRow) == 1
    assert row_count(session_factory, TurnRow) == 1
    assert row_count(session_factory, ArtifactRow) == 2


def test_import_call_changed_manifest_conflicts_without_overwriting_existing_data(
    tmp_path: Path,
    session_factory,
):
    folder = create_call_folder(tmp_path / "call")
    store = LocalArtifactStore(tmp_path / "artifacts")
    importer = CallFolderImporter(session_factory, store, ReadyProcessor())
    first = importer.import_call(folder, "tenant-a")
    original_recording = next(
        path
        for path in store.base_dir.rglob("recording.wav")
        if path.is_file()
    )
    (folder / "call.json").write_text(
        json.dumps(
            {
                "call_id": "import-call",
                "messages": [
                    {"role": "assistant", "content": "Changed", "t": 0.0},
                ],
            }
        ),
        encoding="utf-8",
    )

    conflict = importer.import_call(folder, "tenant-a")

    assert first.status == "created"
    assert conflict.status == "conflict"
    assert conflict.processing is None
    assert conflict.interaction_id == "import-call"
    assert row_count(session_factory, InteractionRow) == 1
    assert row_count(session_factory, OutboxRow) == 1
    assert row_count(session_factory, TurnRow) == 1
    assert row_count(session_factory, ArtifactRow) == 2
    assert original_recording.read_bytes() == (folder / "recording.wav").read_bytes()
    assert len(list(store.base_dir.rglob("call.json"))) == 1


def test_import_call_changed_artifact_conflicts_when_manifest_is_unchanged(
    tmp_path: Path,
    session_factory,
):
    folder = create_call_folder(tmp_path / "call")
    extra_file = folder / "supporting.txt"
    extra_file.write_text("original artifact", encoding="utf-8")
    store = LocalArtifactStore(tmp_path / "artifacts")
    importer = CallFolderImporter(session_factory, store, ReadyProcessor())
    first = importer.import_call(folder, "tenant-a")
    stored_original = next(store.base_dir.rglob("supporting.txt"))
    extra_file.write_text("changed artifact", encoding="utf-8")

    conflict = importer.import_call(folder, "tenant-a")

    assert first.status == "created"
    assert conflict.status == "conflict"
    assert conflict.processing is None
    assert row_count(session_factory, InteractionRow) == 1
    assert row_count(session_factory, OutboxRow) == 1
    assert row_count(session_factory, TurnRow) == 1
    assert row_count(session_factory, ArtifactRow) == 3
    assert stored_original.read_text(encoding="utf-8") == "original artifact"
    assert len(list(store.base_dir.rglob("supporting.txt"))) == 1


def test_import_call_missing_required_file_writes_no_database_rows(
    tmp_path: Path,
    session_factory,
):
    folder = tmp_path / "incomplete"
    folder.mkdir()
    (folder / "call.json").write_text('{"call_id": "missing-recording"}', encoding="utf-8")
    importer = CallFolderImporter(
        session_factory,
        LocalArtifactStore(tmp_path / "artifacts"),
        ReadyProcessor(),
    )

    result = importer.import_call(folder, "tenant-a")

    assert result.status == "invalid"
    assert result.processing is None
    assert result.validation_errors
    assert row_count(session_factory, InteractionRow) == 0
    assert row_count(session_factory, OutboxRow) == 0
    assert row_count(session_factory, TurnRow) == 0
    assert row_count(session_factory, ArtifactRow) == 0


def test_import_call_malformed_manifest_returns_validation_result(
    tmp_path: Path,
    session_factory,
):
    folder = tmp_path / "malformed"
    folder.mkdir()
    (folder / "call.json").write_bytes(b"\xff")
    importer = CallFolderImporter(
        session_factory,
        LocalArtifactStore(tmp_path / "artifacts"),
        ReadyProcessor(),
    )

    result = importer.import_call(folder, "tenant-a")

    assert result.status == "invalid"
    assert result.processing is None
    assert result.interaction_id is None
    assert result.validation_errors
    assert row_count(session_factory, InteractionRow) == 0


def test_import_call_rolls_back_rows_and_removes_new_artifacts_on_persistence_failure(
    tmp_path: Path,
    session_factory,
):
    folder = create_call_folder(tmp_path / "call")
    store = LocalArtifactStore(tmp_path / "artifacts")
    importer = CallFolderImporter(session_factory, store, ReadyProcessor())

    def fail_artifact_insert(
        connection,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        if statement.lstrip().startswith("INSERT INTO interaction_artifacts"):
            raise RuntimeError("forced database failure")

    event.listen(session_factory.engine, "before_cursor_execute", fail_artifact_insert)
    try:
        result = importer.import_call(folder, "tenant-a")
    finally:
        event.remove(
            session_factory.engine,
            "before_cursor_execute",
            fail_artifact_insert,
        )

    assert result.status == "failed"
    assert result.processing is None
    assert result.error
    assert str(folder) not in result.error
    assert row_count(session_factory, InteractionRow) == 0
    assert row_count(session_factory, OutboxRow) == 0
    assert row_count(session_factory, TurnRow) == 0
    assert row_count(session_factory, ArtifactRow) == 0
    assert not [
        path
        for path in store.base_dir.rglob("*")
        if path.is_file()
    ]


def test_post_commit_processing_failure_does_not_change_import_status(
    tmp_path: Path,
    session_factory,
):
    folder = create_call_folder(tmp_path / "call")
    store = LocalArtifactStore(tmp_path / "artifacts")

    class FailedProcessor:
        def process_imported_call(self, folder_path, envelope, turns, validation):
            raise RuntimeError(f"failure at {folder_path}")

    result = CallFolderImporter(
        session_factory,
        store,
        FailedProcessor(),
    ).import_call(folder, "tenant-a")

    assert result.status == "created"
    assert row_count(session_factory, InteractionRow) == 1
    assert row_count(session_factory, TurnRow) == 1
    assert row_count(session_factory, ArtifactRow) == 2
    assert result.processing.timeline_status == "failed"
    assert result.processing.observability_status == "failed"
    assert result.processing.evaluation_status == "failed"
    assert len(result.processing.errors) == 3
    assert str(folder) not in " ".join(
        error.message for error in result.processing.errors
    )


def test_concurrent_failed_import_cannot_delete_successful_artifacts(
    tmp_path: Path,
    session_factory,
    monkeypatch,
):
    folder = create_call_folder(tmp_path / "call")
    store = LocalArtifactStore(tmp_path / "artifacts")
    importer = CallFolderImporter(session_factory, store, ReadyProcessor())
    original_persist = importer._persist_call
    attempts_lock = threading.Lock()
    attempts = 0
    second_persisted = threading.Event()

    def persist_with_one_failure(envelope, turns, artifact_rows):
        nonlocal attempts
        with attempts_lock:
            attempts += 1
            attempt = attempts
        if attempt == 1:
            second_persisted.wait(timeout=0.25)
            raise RuntimeError("forced one-attempt persistence failure")
        result = original_persist(envelope, turns, artifact_rows)
        second_persisted.set()
        return result

    monkeypatch.setattr(importer, "_persist_call", persist_with_one_failure)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: importer.import_call(folder, "tenant-a"),
                range(2),
            )
        )

    assert {result.status for result in results} == {"created", "failed"}
    assert row_count(session_factory, InteractionRow) == 1
    assert row_count(session_factory, ArtifactRow) == 2
    assert len(
        [
            path
            for path in store.base_dir.rglob("*")
            if path.is_file()
        ]
    ) == 2
