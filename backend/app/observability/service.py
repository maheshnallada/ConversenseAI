import json
from pathlib import Path
from typing import Any

from app.domain.envelope import InteractionEvent
from app.domain.observability import InteractionMetrics
from app.domain.transcript import TranscriptTurn
from app.observability.calculator import calculate_interaction_metrics
from app.observability.config import RateCardManager
from app.reconstruction.processor import TranscriptProcessor
from app.storage.observability_repo import ObservabilityRepository
from app.validation.audio import validate_wav


class ObservabilityService:
    def __init__(
        self,
        session_factory,
        rate_card: RateCardManager | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.rate_card = rate_card or RateCardManager()
        self.repo = ObservabilityRepository(session_factory)
        self.turn_processor = TranscriptProcessor()

    def calculate_interaction(
        self,
        tenant_id: str,
        interaction_id: str,
        turns: list[TranscriptTurn],
        events: list[InteractionEvent] | None = None,
        call_data: dict[str, Any] | None = None,
        recording_duration_s: float | None = None,
        recording_silent: bool | None = None,
        calculation_version: str = "1.0",
    ) -> InteractionMetrics:
        metrics = calculate_interaction_metrics(
            tenant_id=tenant_id,
            interaction_id=interaction_id,
            call_data=call_data or {},
            turns=turns,
            recording_duration_s=recording_duration_s,
            rate_card=self.rate_card,
            events=events,
            calculation_version=calculation_version,
            recording_silent=recording_silent,
        )
        self.repo.save_metrics(metrics)
        return metrics

    def process_call_folder(
        self,
        call_folder: Path | str,
        tenant_id: str,
    ) -> InteractionMetrics:
        folder = Path(call_folder).resolve()
        call_json_path = folder / "call.json"
        if not call_json_path.exists():
            raise FileNotFoundError(f"Missing call.json in {folder}")

        with open(call_json_path, "r", encoding="utf-8") as f:
            call_data = json.load(f)

        call_id = call_data["call_id"]

        # Validate recording WAV duration
        recording_wav_path = folder / "recording.wav"
        recording_duration = None
        recording_silent = None
        if recording_wav_path.exists():
            wav_val = validate_wav(recording_wav_path)
            if wav_val.is_valid:
                recording_duration = wav_val.duration_s
                recording_silent = wav_val.is_silent

        turns = self.turn_processor.process_folder(folder, tenant_id=tenant_id)

        return self.calculate_interaction(
            tenant_id=tenant_id,
            interaction_id=call_id,
            turns=turns,
            call_data=call_data,
            recording_duration_s=recording_duration,
            recording_silent=recording_silent,
        )

