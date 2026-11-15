import json
import wave
from pathlib import Path

from sqlalchemy import event, func, select

from app.ingestion.call_importer import CallFolderImporter
from app.storage.artifacts import LocalArtifactStore
from app.storage.orm import ArtifactRow, InteractionRow, OutboxRow, TurnRow


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
):
    folder = create_call_folder(tmp_path / "call")
    store = LocalArtifactStore(tmp_path / "artifacts")
    importer = CallFolderImporter(session_factory, store)

    result = importer.import_call(folder, "tenant-a")

    assert result.status == "created"
    assert result.interaction_id == "import-call"
    assert result.folder_name == "call"
    assert result.files_count == 2
    assert result.audio_validation.is_valid is True
    assert result.audio_validation.channels == 1
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
    importer = CallFolderImporter(
        session_factory,
        LocalArtifactStore(tmp_path / "artifacts"),
    )

    first = importer.import_call(folder, "tenant-a")
    replay = importer.import_call(renamed_folder, "tenant-a")

    assert first.status == "created"
    assert replay.status == "replayed"
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
    importer = CallFolderImporter(session_factory, store)
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
    importer = CallFolderImporter(session_factory, store)
    first = importer.import_call(folder, "tenant-a")
    stored_original = next(store.base_dir.rglob("supporting.txt"))
    extra_file.write_text("changed artifact", encoding="utf-8")

    conflict = importer.import_call(folder, "tenant-a")

    assert first.status == "created"
    assert conflict.status == "conflict"
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
    )

    result = importer.import_call(folder, "tenant-a")

    assert result.status == "invalid"
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
    )

    result = importer.import_call(folder, "tenant-a")

    assert result.status == "invalid"
    assert result.interaction_id is None
    assert result.validation_errors
    assert row_count(session_factory, InteractionRow) == 0


def test_import_call_rolls_back_rows_and_removes_new_artifacts_on_persistence_failure(
    tmp_path: Path,
    session_factory,
):
    folder = create_call_folder(tmp_path / "call")
    store = LocalArtifactStore(tmp_path / "artifacts")
    importer = CallFolderImporter(session_factory, store)

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
