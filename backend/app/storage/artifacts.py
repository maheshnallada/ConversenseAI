import hashlib
import mimetypes
import os
import shutil
import tempfile
import urllib.request
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class StoredArtifact:
    artifact_id: str
    uri: str
    sha256: str
    byte_size: int
    media_type: str
    source_path: str


class ArtifactStore(ABC):
    @abstractmethod
    def put_file(self, source_path: Path | str, relative_dest: str | None = None) -> StoredArtifact:
        pass

    @abstractmethod
    def get_path(self, uri: str) -> Path:
        pass

    @abstractmethod
    def exists(self, uri: str) -> bool:
        pass


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def detect_media_type(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".jsonl"):
        return "application/x-ndjson"
    if name.endswith(".wav"):
        return "audio/wav"
    if name.endswith(".json"):
        return "application/json"
    if name.endswith(".log") or name.endswith(".txt"):
        return "text/plain"
    if name.endswith(".md"):
        return "text/markdown"
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


class LocalArtifactStore(ArtifactStore):
    def __init__(self, base_dir: Path | str | None = None) -> None:
        if base_dir is None:
            env_path = (
                os.getenv("ARTIFACT_STORAGE_PATH")
                or os.getenv("ARTIFACT_STORE_PATH")
                or os.getenv("ARTIFACTS_DIR")
            )
            if env_path:
                target_dir = Path(env_path)
            else:
                target_dir = Path("backend/storage/artifacts")
        else:
            target_dir = Path(base_dir)

        self.base_dir = target_dir.resolve()
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            # Test write access to catch read-only mounts (e.g. Errno 30)
            test_file = self.base_dir / ".write_test"
            test_file.touch(exist_ok=True)
            test_file.unlink(missing_ok=True)
        except OSError:
            # Fallback to temp directory if base_dir is read-only
            fallback = Path(tempfile.gettempdir()) / "conversense_artifacts"
            fallback.mkdir(parents=True, exist_ok=True)
            self.base_dir = fallback.resolve()

    def put_file(self, source_path: Path | str, relative_dest: str | None = None) -> StoredArtifact:
        src = Path(source_path).resolve()
        if not src.exists():
            raise FileNotFoundError(f"Source file not found: {src}")

        digest = compute_sha256(src)
        byte_size = src.stat().st_size
        media_type = detect_media_type(src)

        if relative_dest is None:
            # Deterministic subfolder layout based on hash prefix
            relative_dest = f"{digest[:2]}/{digest[2:4]}/{digest}_{src.name}"

        dest = (self.base_dir / relative_dest).resolve()
        dest_stored = False
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(src, dest)
            dest_stored = True
        except OSError:
            # Fallback to system temp directory if base_dir is read-only
            try:
                temp_dest = (Path(tempfile.gettempdir()) / "conversense_artifacts" / relative_dest).resolve()
                temp_dest.parent.mkdir(parents=True, exist_ok=True)
                if not temp_dest.exists():
                    shutil.copy2(src, temp_dest)
                dest = temp_dest
                dest_stored = True
            except OSError:
                dest_stored = False

        # If dest was successfully stored, use its URI; otherwise reference existing source file directly
        final_path = dest if dest_stored and dest.exists() else src
        uri = final_path.as_uri()
        artifact_id = str(uuid.uuid5(uuid.NAMESPACE_URL, uri))

        return StoredArtifact(
            artifact_id=artifact_id,
            uri=uri,
            sha256=digest,
            byte_size=byte_size,
            media_type=media_type,
            source_path=str(src),
        )

    def get_path(self, uri: str) -> Path:
        if uri.startswith("file://"):
            parsed = urlparse(uri)
            p = Path(urllib.request.url2pathname(parsed.path))
            if not p.exists():
                # Cross-platform fallback for Windows vs POSIX URI formats
                raw_path = uri[8:] if uri.startswith("file:///") else uri[7:]
                p_alt = Path(raw_path)
                if p_alt.exists():
                    return p_alt
                raise FileNotFoundError(f"Artifact not found: {uri}")
            return p
        raise ValueError(f"Unsupported URI scheme: {uri}")

    def exists(self, uri: str) -> bool:
        try:
            return self.get_path(uri).exists()
        except (ValueError, FileNotFoundError):
            return False

