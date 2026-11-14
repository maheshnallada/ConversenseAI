from dataclasses import dataclass, field
from typing import Any, Literal

from app.reconstruction.failures import FailureRecord


@dataclass
class TimelineEvent:
    event_id: str
    event_type: str
    speaker: str | None = None
    start_s: float | None = None
    end_s: float | None = None
    duration_s: float | None = None
    text: str | None = None
    delivery_status: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReconstructedTimeline:
    tenant_id: str
    interaction_id: str
    total_duration_s: float
    agent_turn_count: int
    customer_turn_count: int
    overlap_count: int
    total_overlap_s: float
    events: list[TimelineEvent]
    first_technical_failure: FailureRecord | None = None
    first_conversational_failure: FailureRecord | None = None

    @property
    def first_agent_speech_s(self) -> float | None:
        agent_turn_starts = [
            event.start_s
            for event in self.events
            if event.event_type == "turn"
            and event.speaker == "agent"
            and event.start_s is not None
        ]
        return min(agent_turn_starts) if agent_turn_starts else None

