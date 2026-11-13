import json
from pathlib import Path
from typing import Any

from app.domain.observability import InteractionMetrics
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
        if recording_wav_path.exists():
            wav_val = validate_wav(recording_wav_path)
            if wav_val.is_valid:
                recording_duration = wav_val.duration_s

        # Extract turns
        turns = self.turn_processor.process_folder(folder, tenant_id=tenant_id)

        # Calculate metrics
        metrics = calculate_interaction_metrics(
            tenant_id=tenant_id,
            interaction_id=call_id,
            call_data=call_data,
            turns=turns,
            recording_duration_s=recording_duration,
            rate_card=self.rate_card,
        )

        # Save to database
        self.repo.save_metrics(metrics)

        return metrics

