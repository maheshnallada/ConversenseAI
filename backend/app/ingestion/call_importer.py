import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.ingestion.errors import IdempotencyConflict
from app.ingestion.mapper import map_call_folder_with_artifact_tracking
from app.ingestion.post_import_processor import (
    CallProcessingError,
    CallProcessingSummary,
    PostImportProcessor,
)
from app.ingestion.service import IngestionService, canonical_json, payload_hash
from app.reconstruction.processor import TranscriptProcessor
from app.storage.artifacts import ArtifactStore, StoredArtifact
from app.storage.orm import ArtifactRow, InteractionRow
from app.storage.stage_repo import StageRepository
from app.storage.transcript_repo import TranscriptRepository, TranscriptTurnConflict
from app.validation.audio import (
    CallFilesValidationResult,
    validate_call_files,
    validate_wav,
)

logger = logging.getLogger(__name__)
_IMPORT_LOCKS = tuple(threading.Lock() for _ in range(64))


@dataclass(frozen=True)
class AudioValidationSummary:
    is_valid: bool
    channels: int | None = None
    sample_rate: int | None = None
    sample_width: int | None = None
    duration_s: float | None = None
    is_silent: bool = False


@dataclass(frozen=True)
class CallImportResult:
    folder_name: str
    interaction_id: str | None
    status: Literal["created", "replayed", "invalid", "conflict", "failed"]
    files_count: int
    audio_validation: AudioValidationSummary
    validation_errors: list[str] = field(default_factory=list)
    error: str | None = None
    has_agent_manifest: bool = False
    phone_answered: bool = False
    processing: CallProcessingSummary | None = None


class CallFolderImporter:
    def __init__(
        self,
        session_factory,
        artifact_store: ArtifactStore,
        post_import_processor: PostImportProcessor | None = None,
        async_mode: bool = False,
    ) -> None:
        self._session_factory = session_factory
        self._artifact_store = artifact_store
        self._ingestion = IngestionService(session_factory)
        self._transcript_processor = TranscriptProcessor()
        self._transcript_repository = TranscriptRepository(session_factory)
        self._stage_repo = StageRepository(session_factory)
        self._async_mode = async_mode
        self._post_import_processor = (
            post_import_processor
            if post_import_processor is not None
            else PostImportProcessor(session_factory)
        )

    def import_call(
        self,
        folder_path: Path,
        tenant_id: str,
        async_mode: bool | None = None,
    ) -> CallImportResult:
        use_async = self._async_mode if async_mode is None else async_mode
        folder = Path(folder_path)
        folder_name = folder.name
        files_count = self._count_files(folder)
        interaction_id = self._read_call_id(folder)
        validation = validate_call_files(folder)
        audio_validation = self._audio_validation(folder)
        if not validation.is_valid:
            return self._result(
                folder_name,
                interaction_id,
                "invalid",
                files_count,
                audio_validation,
                validation,
            )

        interaction_lock = self._import_lock(tenant_id, interaction_id or "")
        interaction_lock.acquire()
        try:
            stored_artifacts: list[StoredArtifact] = []
            envelope: InteractionEnvelope | None = None
            artifact_rows: list[ArtifactRow] = []
            turns: list[TranscriptTurn] = []
            try:
                mapped_envelope, artifact_rows, validation, stored_artifacts = (
                    map_call_folder_with_artifact_tracking(
                        folder,
                        tenant_id,
                        self._artifact_store,
                        stored_artifacts=stored_artifacts,
                    )
                )
                envelope = mapped_envelope
                if not validation.is_valid:
                    cleanup_complete = self._cleanup_created(stored_artifacts)
                    interaction_id = mapped_envelope.interaction_id
                    result = self._result(
                        folder_name,
                        envelope.interaction_id,
                        "invalid",
                        files_count,
                        audio_validation,
                        validation,
                        error=(
                            None
                            if cleanup_complete
                            else "Artifact cleanup was incomplete."
                        ),
                    )
                    return result
                interaction_id = mapped_envelope.interaction_id
                turns = self._transcript_processor.process_folder(folder, tenant_id)
                status = self._persist_call(mapped_envelope, turns, artifact_rows)
            except (IdempotencyConflict, TranscriptTurnConflict, IntegrityError):
                status = self._existing_status(
                    envelope,
                    artifact_rows,
                )
                if status is None:
                    cleanup_complete = self._cleanup_created(stored_artifacts)
                    logger.exception("Call folder import failed during persistence")
                    return self._failed_result(
                        folder_name,
                        interaction_id,
                        files_count,
                        audio_validation,
                        validation,
                        cleanup_complete,
                    )
            except Exception:
                cleanup_complete = self._cleanup_created(stored_artifacts)
                logger.exception("Call folder import failed")
                return self._failed_result(
                    folder_name,
                    interaction_id,
                    files_count,
                    audio_validation,
                    validation,
                    cleanup_complete,
                )
            if envelope is not None:
                interaction_id = envelope.interaction_id
            cleanup_complete = True
            if status != "created":
                cleanup_complete = self._cleanup_created(stored_artifacts)
            error = (
                "Call content differs from the previously imported version."
                if status == "conflict"
                else None
            )
            if not cleanup_complete:
                error = (
                    f"{error} Artifact cleanup was incomplete."
                    if error
                    else "Artifact cleanup was incomplete."
                )
            result = self._result(
                folder_name,
                interaction_id,
                status,
                files_count,
                audio_validation,
                validation,
                error=error,
            )
        finally:
            interaction_lock.release()

        if status not in {"created", "replayed"} or envelope is None:
            return result

        if use_async:
            self._stage_repo.record_stage_start(
                tenant_id=tenant_id,
                interaction_id=envelope.interaction_id,
                stage_name="general",
            )
            processing = CallProcessingSummary(
                transcript_turns=len(turns),
                timeline_status="ready",
                observability_status="ready",
                evaluation_status="ready",
                evaluation_run_id=None,
            )
            return replace(result, processing=processing)

        try:
            processing = self._post_import_processor.process_imported_call(
                folder,
                envelope,
                turns,
                validation,
            )
        except Exception:
            logger.exception(
                "Unexpected post-import processing failure for %s",
                envelope.interaction_id,
            )
            processing = CallProcessingSummary(
                transcript_turns=len(turns),
                timeline_status="failed",
                observability_status="failed",
                evaluation_status="failed",
                evaluation_run_id=None,
                errors=[
                    CallProcessingError(stage, f"{stage.title()} processing failed.")
                    for stage in ("timeline", "observability", "evaluation")
                ],
            )
        return replace(result, processing=processing)

    @staticmethod
    def _import_lock(tenant_id: str, interaction_id: str) -> threading.Lock:
        key = hashlib.sha256(
            f"{tenant_id}\0{interaction_id}".encode("utf-8")
        ).digest()
        stripe = int.from_bytes(key[:8], byteorder="big") % len(_IMPORT_LOCKS)
        return _IMPORT_LOCKS[stripe]

    def _persist_call(
        self,
        envelope: InteractionEnvelope,
        turns: list[TranscriptTurn],
        artifact_rows: list[ArtifactRow],
    ) -> Literal["created", "replayed", "conflict"]:
        with self._session_factory.begin() as session:
            ingest_result = self._ingestion.ingest_in_session(session, envelope)
            if not ingest_result.created:
                status = self._existing_status_in_session(
                    session,
                    envelope,
                    artifact_rows,
                )
                return status or "conflict"

            for turn in turns:
                self._transcript_repository.save_turn(turn, session=session)
            session.add_all(artifact_rows)
        return "created"

    def _existing_status(
        self,
        envelope: InteractionEnvelope | None,
        artifact_rows: list[ArtifactRow],
    ) -> Literal["replayed", "conflict"] | None:
        if envelope is None:
            return None
        with self._session_factory() as session:
            return self._existing_status_in_session(session, envelope, artifact_rows)

    @staticmethod
    def _existing_status_in_session(
        session: Session,
        envelope: InteractionEnvelope,
        artifact_rows: list[ArtifactRow],
    ) -> Literal["replayed", "conflict"] | None:
        existing = session.scalar(
            select(InteractionRow).where(
                InteractionRow.tenant_id == envelope.tenant_id,
                InteractionRow.interaction_id == envelope.interaction_id,
            )
        )
        if existing is None:
            return None
        existing_hashes = session.scalars(
            select(ArtifactRow.sha256).where(
                ArtifactRow.tenant_id == envelope.tenant_id,
                ArtifactRow.interaction_id == envelope.interaction_id,
            )
        ).all()
        expected_hashes = [artifact.sha256 for artifact in artifact_rows]
        if (
            existing.payload_hash == payload_hash(canonical_json(envelope))
            and sorted(existing_hashes) == sorted(expected_hashes)
        ):
            return "replayed"
        return "conflict"

    def _audio_validation(self, folder: Path) -> AudioValidationSummary:
        result = validate_wav(folder / "recording.wav")
        return AudioValidationSummary(
            is_valid=result.is_valid,
            channels=result.channels,
            sample_rate=result.sample_rate,
            sample_width=result.sample_width,
            duration_s=result.duration_s,
            is_silent=result.is_silent,
        )

    @staticmethod
    def _read_call_id(folder: Path) -> str | None:
        try:
            with open(folder / "call.json", "r", encoding="utf-8") as call_file:
                data = json.load(call_file)
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        call_id = data.get("call_id") if isinstance(data, dict) else None
        return call_id if isinstance(call_id, str) and call_id.strip() else None

    @staticmethod
    def _count_files(folder: Path) -> int:
        if not folder.is_dir():
            return 0
        return sum(
            1
            for path in folder.rglob("*")
            if path.is_file() and not path.is_symlink()
        )

    def _cleanup_created(self, artifacts: list[StoredArtifact]) -> bool:
        clean = True
        for artifact in artifacts:
            if not artifact.created:
                continue
            try:
                self._artifact_store.delete(artifact.uri)
            except (OSError, ValueError):
                clean = False
                logger.exception("Failed to clean up an uncommitted call artifact")
        return clean

    def _failed_result(
        self,
        folder_name: str,
        interaction_id: str | None,
        files_count: int,
        audio_validation: AudioValidationSummary,
        validation: CallFilesValidationResult,
        cleanup_complete: bool,
    ) -> CallImportResult:
        error = "Import failed; no call data was saved."
        if not cleanup_complete:
            error = f"{error} Artifact cleanup was incomplete."
        return self._result(
            folder_name,
            interaction_id,
            "failed",
            files_count,
            audio_validation,
            validation,
            error=error,
        )

    @staticmethod
    def _result(
        folder_name: str,
        interaction_id: str | None,
        status: Literal["created", "replayed", "invalid", "conflict", "failed"],
        files_count: int,
        audio_validation: AudioValidationSummary,
        validation: CallFilesValidationResult,
        error: str | None = None,
    ) -> CallImportResult:
        return CallImportResult(
            folder_name=folder_name,
            interaction_id=interaction_id,
            status=status,
            files_count=files_count,
            audio_validation=audio_validation,
            validation_errors=list(validation.errors),
            error=error,
            has_agent_manifest=validation.has_agent_manifest,
            phone_answered=validation.phone_answered,
        )
