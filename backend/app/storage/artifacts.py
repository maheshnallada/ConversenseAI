import hashlib
import mimetypes
import shutil
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


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
    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

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
        dest.parent.mkdir(parents=True, exist_ok=True)

        if not dest.exists():
            shutil.copy2(src, dest)

        uri = dest.as_uri()
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
        if uri.startswith("file:///"):
            # Windows path handling for file:/// URI
            raw_path = uri[8:]
            # e.g., C:/Users/...
            p = Path(raw_path)
            if not p.exists():
                raise FileNotFoundError(f"Artifact not found: {uri}")
            return p
        raise ValueError(f"Unsupported URI scheme: {uri}")

    def exists(self, uri: str) -> bool:
        try:
            return self.get_path(uri).exists()
        except (ValueError, FileNotFoundError):
            return False

