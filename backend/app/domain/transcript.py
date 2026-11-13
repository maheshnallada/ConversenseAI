from dataclasses import dataclass, field
from typing import Any, Literal

SpeakerRole = Literal["agent", "customer", "system", "unknown"]
PlaybackSpokenStatus = Literal["heard", "cut", "not_played", "no_audio"]


@dataclass
class TranscriptTurn:
    turn_id: str
    interaction_id: str
    tenant_id: str
    turn_index: int
    speaker: str
    raw_text: str
    normalized_text: str
    start_s: float | None = None
    end_s: float | None = None
    duration_s: float | None = None
    playback_spoken: str | None = None
    playback_heard_text: str | None = None
    audio_s: float | None = None
    barged_in: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

