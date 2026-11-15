import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.evaluation.service import EvaluationService
from app.observability.service import ObservabilityService
from app.reconstruction.reconstructor import TimelineReconstructor
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.observability_repo import ObservabilityRepository
from app.storage.timeline_repo import TimelineRepository
from app.validation.audio import CallFilesValidationResult, validate_wav

logger = logging.getLogger(__name__)

ProcessingStage = Literal["timeline", "observability", "evaluation"]
ProcessingStatus = Literal["ready", "failed"]


@dataclass(frozen=True)
class CallProcessingError:
    stage: ProcessingStage
    message: str


@dataclass(frozen=True)
class CallProcessingSummary:
    transcript_turns: int
    timeline_status: ProcessingStatus
    observability_status: ProcessingStatus
    evaluation_status: ProcessingStatus
    evaluation_run_id: str | None
    errors: list[CallProcessingError] = field(default_factory=list)


class PostImportProcessor:
    def __init__(self, session_factory) -> None:
        self._timeline_reconstructor = TimelineReconstructor()
        self._timeline_repository = TimelineRepository(session_factory)
        self._observability_service = ObservabilityService(session_factory)
        self._observability_repository = ObservabilityRepository(session_factory)
        self._evaluation_service = EvaluationService(session_factory)
        self._evaluation_repository = EvaluationRepository(session_factory)

    def process_imported_call(
        self,
        folder_path: Path,
        envelope: InteractionEnvelope,
        turns: list[TranscriptTurn],
        validation: CallFilesValidationResult,
    ) -> CallProcessingSummary:
        errors: list[CallProcessingError] = []
        timeline_status: ProcessingStatus = "ready"
        observability_status: ProcessingStatus = "ready"

        try:
            if self._timeline_repository.get_timeline(
                envelope.tenant_id,
                envelope.interaction_id,
            ) is None:
                timeline = self._timeline_reconstructor.reconstruct(
                    tenant_id=envelope.tenant_id,
                    interaction_id=envelope.interaction_id,
                    turns=turns,
                    call_metadata=(envelope.domain_data or {}).get("meta"),
                    events=envelope.events,
                )
                self._timeline_repository.save_timeline(timeline)
        except Exception:
            logger.exception(
                "Failed to process imported call timeline for %s",
                envelope.interaction_id,
            )
            timeline_status = "failed"
            errors.append(
                CallProcessingError("timeline", "Timeline processing failed.")
            )

        try:
            if self._observability_repository.get_metrics(
                envelope.tenant_id,
                envelope.interaction_id,
            ) is None:
                call_data = self._read_call_data(folder_path)
                recording = validate_wav(Path(folder_path) / "recording.wav")
                self._observability_service.calculate_interaction(
                    tenant_id=envelope.tenant_id,
                    interaction_id=envelope.interaction_id,
                    turns=turns,
                    events=envelope.events,
                    call_data=call_data,
                    recording_duration_s=(
                        recording.duration_s if recording.is_valid else None
                    ),
                    recording_silent=(
                        recording.is_silent if recording.is_valid else None
                    ),
                )
        except Exception:
            logger.exception(
                "Failed to process imported call observability for %s",
                envelope.interaction_id,
            )
            observability_status = "failed"
            errors.append(
                CallProcessingError(
                    "observability",
                    "Observability processing failed.",
                )
            )

        evaluation_run_id: str | None = None
        evaluation_status: ProcessingStatus = "ready"
        try:
            run = self._evaluation_repository.get_latest_run(
                envelope.tenant_id,
                envelope.interaction_id,
            )
            if run is None:
                run = self._evaluation_service.evaluate_interaction(
                    envelope.tenant_id,
                    envelope.interaction_id,
                )
            evaluation_run_id = run.run_id
            if any(batch.status == "failed" for batch in run.batches):
                evaluation_status = "failed"
                if not any(error.stage == "evaluation" for error in errors):
                    errors.append(
                        CallProcessingError(
                            "evaluation",
                            "One or more evaluation batches failed.",
                        )
                    )
        except Exception:
            logger.exception(
                "Failed to process imported call evaluation for %s",
                envelope.interaction_id,
            )
            evaluation_status = "failed"
            errors.append(
                CallProcessingError("evaluation", "Evaluation processing failed.")
            )

        return CallProcessingSummary(
            transcript_turns=len(turns),
            timeline_status=timeline_status,
            observability_status=observability_status,
            evaluation_status=evaluation_status,
            evaluation_run_id=evaluation_run_id,
            errors=errors,
        )

    @staticmethod
    def _read_call_data(folder_path: Path) -> dict:
        with (Path(folder_path) / "call.json").open("r", encoding="utf-8") as file:
            call_data = json.load(file)
        if not isinstance(call_data, dict):
            raise ValueError("call.json must contain an object.")
        return call_data
