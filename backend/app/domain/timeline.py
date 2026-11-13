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

