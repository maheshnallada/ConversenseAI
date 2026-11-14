from pathlib import Path
import pytest

from app.ingestion.mapper import map_call_folder
from app.storage.artifacts import LocalArtifactStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CALLS_DIR = PROJECT_ROOT / "backend" / "storage" / "artifacts" / "health_campaign"


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

