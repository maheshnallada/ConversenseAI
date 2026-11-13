from dataclasses import dataclass, field
from typing import Any

from app.observability.config import CostBreakdown


@dataclass
class PercentilesResult:
    avg: float | None = None
    p50: float | None = None
    p90: float | None = None
    p95: float | None = None
    p99: float | None = None


@dataclass
class InteractionMetrics:
    tenant_id: str
    interaction_id: str
    recording_duration_s: float | None
    telephony_duration_s: float | None
    turn_count: int
    agent_turn_count: int
    customer_turn_count: int
    first_agent_latency_s: float | None
    response_latency_percentiles: PercentilesResult
    longest_silence_s: float | None
    overlap_count: int
    total_overlap_s: float
    audio_missing: bool
    audio_silent: bool
    llm_provider: str | None
    llm_model: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cost_breakdown: CostBreakdown


@dataclass
class PlatformObservabilitySummary:
    total_interactions: int
    total_recording_duration_s: float
    total_telephony_duration_s: float
    total_turns: int
    total_agent_turns: int
    total_customer_turns: int
    overall_latency_percentiles: PercentilesResult
    total_overlap_count: int
    total_overlap_duration_s: float
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float
    currency: str = "USD"

