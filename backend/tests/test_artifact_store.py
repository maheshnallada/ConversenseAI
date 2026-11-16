from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.app import create_app
from app.storage.artifacts import LocalArtifactStore, StoredArtifact


def test_put_file_stores_content_and_metadata(tmp_path: Path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    sample_file = source_dir / "sample.json"
    sample_file.write_text('{"test": 123}', encoding="utf-8")

    storage_dir = tmp_path / "artifacts"
    store = LocalArtifactStore(base_dir=storage_dir)

    stored: StoredArtifact = store.put_file(sample_file, relative_dest="tenant_001/call_01/sample.json")

    assert stored.artifact_id is not None
    assert stored.byte_size == len(sample_file.read_bytes())
    assert stored.media_type == "application/json"
    assert stored.source_path == str(sample_file.resolve())
    assert stored.uri.startswith("file://")
    assert Path(store.get_path(stored.uri)).exists()
    assert Path(store.get_path(stored.uri)).read_text(encoding="utf-8") == '{"test": 123}'
    assert store.exists(stored.uri) is True


def test_put_file_reports_creation_and_delete_removes_only_new_stored_file(
    tmp_path: Path,
):
    source = tmp_path / "source.txt"
    source.write_text("artifact content", encoding="utf-8")
    store = LocalArtifactStore(tmp_path / "artifacts")

    first = store.put_file(source, relative_dest="imports/content.txt")
    replay = store.put_file(source, relative_dest="imports/content.txt")

    assert first.created is True
    assert replay.created is False
    assert store.delete(first.uri) is True
    assert store.exists(first.uri) is False
    assert source.read_text(encoding="utf-8") == "artifact content"


def test_delete_rejects_files_outside_artifact_store(tmp_path: Path):
    source = tmp_path / "source.txt"
    source.write_text("keep this file", encoding="utf-8")
    store = LocalArtifactStore(tmp_path / "artifacts")

    with pytest.raises(ValueError):
        store.delete(source.as_uri())

    assert source.exists()


def test_wav_media_type_detection(tmp_path: Path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    sample_wav = source_dir / "audio.wav"
    sample_wav.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00" + b"\x00" * 20)

    store = LocalArtifactStore(base_dir=tmp_path / "artifacts")
    stored = store.put_file(sample_wav)

    assert stored.media_type == "audio/wav"
    assert stored.byte_size == len(sample_wav.read_bytes())


def test_nonexistent_uri_returns_false_and_raises(tmp_path: Path):
    store = LocalArtifactStore(base_dir=tmp_path / "artifacts")
    fake_uri = "file:///non/existent/path.wav"
    assert store.exists(fake_uri) is False
    with pytest.raises(FileNotFoundError):
        store.get_path(fake_uri)


def test_initialization_preserves_preexisting_write_test_artifact(tmp_path: Path):
    storage_dir = tmp_path / "artifacts"
    storage_dir.mkdir()
    existing_probe = storage_dir / ".write_test"
    existing_probe.write_text("keep this artifact", encoding="utf-8")

    LocalArtifactStore(base_dir=storage_dir)

    assert existing_probe.read_text(encoding="utf-8") == "keep this artifact"


def test_readonly_filesystem_fallback(tmp_path: Path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    sample = source_dir / "test.json"
    sample.write_text('{"status": "ok"}', encoding="utf-8")

    # Simulate read-only directory
    store = LocalArtifactStore(base_dir=tmp_path / "artifacts")
    
    # Force put_file destination mkdir to fail with Errno 30 (Read-only file system)
    orig_mkdir = Path.mkdir
    def mock_mkdir(self, *args, **kwargs):
        if self == store.base_dir or store.base_dir in self.parents:
            err = OSError(30, "Read-only file system")
            err.errno = 30
            raise err
        return orig_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mock_mkdir)

    stored = store.put_file(sample, relative_dest="tenant_1/call_18/test.json")
    assert stored.artifact_id is not None
    assert store.exists(stored.uri) is True
    assert Path(store.get_path(stored.uri)).exists()


def test_put_file_fails_when_configured_and_fallback_storage_are_unavailable(
    tmp_path: Path,
    monkeypatch,
):
    source = tmp_path / "source.txt"
    source.write_text("artifact content", encoding="utf-8")
    store = LocalArtifactStore(tmp_path / "artifacts")
    original_mkdir = Path.mkdir

    def fail_storage_mkdir(path, *args, **kwargs):
        if "artifacts" in str(path) or "conversense_artifacts" in str(path):
            raise OSError("storage unavailable")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_storage_mkdir)

    with pytest.raises(OSError, match="storage unavailable"):
        store.put_file(source, relative_dest="imports/source.txt")

    assert source.exists()


def test_artifact_reference_registration_keeps_optional_metadata_null(
    session_factory,
):
    client = TestClient(create_app(session_factory))
    interaction = client.post(
        "/api/v1/interactions",
        headers={"X-Tenant-Id": "tenant-a"},
        json={
            "tenant_id": "tenant-a",
            "interaction_id": "call-1",
            "schema_version": "1.0",
        },
    )
    assert interaction.status_code == 201

    response = client.post(
        "/api/v1/interactions/call-1/artifacts",
        headers={"X-Tenant-Id": "tenant-a"},
        json={"artifact_id": "recording-1", "artifact_type": "recording"},
    )
    other_tenant = client.post(
        "/api/v1/interactions/call-1/artifacts",
        headers={"X-Tenant-Id": "tenant-b"},
        json={"artifact_id": "recording-2", "artifact_type": "recording"},
    )
    missing_tenant = client.post(
        "/api/v1/interactions/call-1/artifacts",
        json={"artifact_id": "recording-3", "artifact_type": "recording"},
    )
    missing_interaction = client.post(
        "/api/v1/interactions/missing/artifacts",
        headers={"X-Tenant-Id": "tenant-a"},
        json={"artifact_id": "recording-4", "artifact_type": "recording"},
    )

    assert response.status_code == 201
    assert response.json()["created"] is True
    assert other_tenant.status_code == 404
    assert missing_tenant.status_code == 401
    assert missing_interaction.status_code == 404
    with session_factory() as session:
        row = session.execute(
            text(
                "SELECT artifact_type, uri, media_type, sha256 "
                "FROM interaction_artifact_references "
                "WHERE tenant_id = 'tenant-a' AND interaction_id = 'call-1' "
                "AND artifact_id = 'recording-1'"
            )
        ).one()
    assert row.artifact_type == "recording"
    assert row.uri is None
    assert row.media_type is None
    assert row.sha256 is None


