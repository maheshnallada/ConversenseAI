import json
import wave
from pathlib import Path
import pytest

from app.ingestion.mapper import map_call_folder
from app.storage.artifacts import LocalArtifactStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CALLS_DIR = PROJECT_ROOT / "backend" / "storage" / "artifacts" / "health_campaign"


def create_minimal_call_folder(parent: Path, folder_name: str, call_id: str) -> Path:
    call_folder = parent / folder_name
    call_folder.mkdir(parents=True)
    (call_folder / "call.json").write_text(
        json.dumps({"call_id": call_id}),
        encoding="utf-8",
    )
    with wave.open(str(call_folder / "recording.wav"), "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        recording.writeframes(b"\x01\x00" * 1600)
    return call_folder


def test_map_call_01_standard_call(tmp_path: Path):
    call_01_dir = CALLS_DIR / "call_01"
    assert call_01_dir.exists(), f"call_01 not found at {call_01_dir}"

    store = LocalArtifactStore(base_dir=tmp_path / "artifacts")
    envelope, artifact_rows, validation = map_call_folder(call_01_dir, "tenant_test", store)

    assert envelope.tenant_id == "tenant_test"
    assert len(envelope.interaction_id) == 36
    assert envelope.use_case == "health_insurance"
    assert envelope.interaction_type == "voice"
    assert envelope.schema_version == "1.0"
    assert envelope.status in ["completed", "abandoned"]
    assert envelope.execution is not None
    assert envelope.execution.provider is not None
    assert envelope.artifacts is not None
    assert len(envelope.artifacts) == len(artifact_rows)
    # call_01 has 13 files
    assert len(artifact_rows) == 13
    assert validation.is_valid is True
    assert validation.has_agent_manifest is True


def test_map_call_12_no_agent_audio(tmp_path: Path):
    call_12_dir = CALLS_DIR / "call_12"
    assert call_12_dir.exists()

    store = LocalArtifactStore(base_dir=tmp_path / "artifacts")
    envelope, artifact_rows, validation = map_call_folder(call_12_dir, "tenant_test", store)

    assert envelope.tenant_id == "tenant_test"
    assert validation.has_agent_manifest is False
    assert validation.agent_wav_count == 0
    # call_12 has 6 files
    assert len(artifact_rows) == 6


def test_map_call_13_digital_silence(tmp_path: Path):
    call_13_dir = CALLS_DIR / "call_13"
    assert call_13_dir.exists()

    store = LocalArtifactStore(base_dir=tmp_path / "artifacts")
    envelope, artifact_rows, validation = map_call_folder(call_13_dir, "tenant_test", store)

    assert envelope.tenant_id == "tenant_test"
    assert validation.has_agent_manifest is False
    assert validation.user_wav_count == 1
    # call_13 has 5 files
    assert len(artifact_rows) == 5
    # Check that recording.wav was marked silent
    rec_art = next(a for a in artifact_rows if a.artifact_type == "recording")
    assert rec_art.validation_status == "silent"


def test_map_call_folder_accepts_minimal_folder_and_preserves_nested_files(
    tmp_path: Path,
):
    call_folder = create_minimal_call_folder(tmp_path, "upload-name", "stable-call")
    nested_file = call_folder / "metadata" / "details.txt"
    nested_file.parent.mkdir()
    nested_file.write_text("extra call metadata", encoding="utf-8")
    store = LocalArtifactStore(base_dir=tmp_path / "artifacts")

    envelope, artifact_rows, validation = map_call_folder(
        call_folder,
        "tenant_test",
        store,
    )

    assert validation.is_valid is True
    assert envelope.interaction_id == "stable-call"
    assert len(artifact_rows) == 3
    nested_artifact = next(
        row for row in artifact_rows if row.source_path.endswith("details.txt")
    )
    stored_path = store.get_path(nested_artifact.uri)
    assert stored_path.read_text(encoding="utf-8") == "extra call metadata"
    assert stored_path.relative_to(store.base_dir).as_posix().endswith(
        "metadata/details.txt"
    )


def test_map_call_folder_does_not_use_source_folder_name_as_identity(
    tmp_path: Path,
):
    first_folder = create_minimal_call_folder(tmp_path, "first-name", "stable-call")
    second_folder = create_minimal_call_folder(
        tmp_path,
        "renamed-folder",
        "stable-call",
    )
    store = LocalArtifactStore(base_dir=tmp_path / "artifacts")

    first_envelope, _, _ = map_call_folder(first_folder, "tenant_test", store)
    second_envelope, _, _ = map_call_folder(second_folder, "tenant_test", store)

    assert first_envelope.model_dump(mode="json") == second_envelope.model_dump(
        mode="json"
    )

