from pathlib import Path
import pytest
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
        if "artifacts" in str(self):
            err = OSError(30, "Read-only file system")
            err.errno = 30
            raise err
        return orig_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mock_mkdir)

    stored = store.put_file(sample, relative_dest="tenant_1/call_18/test.json")
    assert stored.artifact_id is not None
    assert store.exists(stored.uri) is True
    assert Path(store.get_path(stored.uri)).exists()


