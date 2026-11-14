from __future__ import annotations

import math
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
class TimelineReconciliation:
    state: Literal["complete", "unknown", "review_required"]
    review_required: bool
    playback_status_counts: dict[str, int] = field(default_factory=dict)
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    unknown_turn_indices: list[int] = field(default_factory=list)
    source_events: list[dict[str, Any]] = field(default_factory=list)
    timestamp_quality: str = "unknown"
    timed_turn_count: int = 0
    timestamp_missing_turn_count: int = 0
    timestamp_invalid_turn_count: int = 0


@dataclass
class ReconstructedTimeline:
    tenant_id: str
    interaction_id: str
    total_duration_s: float | None
    agent_turn_count: int
    customer_turn_count: int
    overlap_count: int
    total_overlap_s: float
    events: list[TimelineEvent]
    first_technical_failure: FailureRecord | None = None
    first_conversational_failure: FailureRecord | None = None
    reconciliation: TimelineReconciliation | None = None
    technical_failure_ordering_unknown: bool = False
    conversational_failure_ordering_unknown: bool = False
    failures: list[FailureRecord] = field(default_factory=list)

    @property
    def first_agent_speech_s(self) -> float | None:
        agent_turns = [
            event
            for event in self.events
            if event.event_type == "turn" and event.speaker == "agent"
        ]
        if not agent_turns or any(
            event.start_s is None
            or event.end_s is None
            or not math.isfinite(event.start_s)
            or not math.isfinite(event.end_s)
            or event.start_s < 0.0
            or event.end_s < event.start_s
            for event in agent_turns
        ):
            return None
        return min(event.start_s for event in agent_turns if event.start_s is not None)

