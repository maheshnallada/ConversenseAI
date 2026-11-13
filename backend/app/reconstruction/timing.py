from dataclasses import dataclass
from typing import Literal

from app.domain.transcript import TranscriptTurn


@dataclass
class TurnTimingAnalysis:
    prev_turn_index: int
    next_turn_index: int
    overlap_s: float
    is_interruption: bool
    interrupter: str | None
    response_latency_s: float | None
    silence_gap_s: float | None


def calculate_overlap(
    t1_start: float | None,
    t1_end: float | None,
    t2_start: float | None,
    t2_end: float | None,
) -> float:
    if t1_start is None or t1_end is None or t2_start is None or t2_end is None:
        return 0.0
    overlap = max(0.0, min(t1_end, t2_end) - max(t1_start, t2_start))
    return round(overlap, 3)


def calculate_response_latency(
    prev_end: float | None,
    next_start: float | None,
) -> float | None:
    if prev_end is None or next_start is None:
        return None
    diff = next_start - prev_end
    if diff < 0:
        # Overlapping turns must not report a negative response latency
        return None
    return round(diff, 3)


def analyze_turn_pair(
    prev_turn: TranscriptTurn,
    next_turn: TranscriptTurn,
) -> TurnTimingAnalysis:
    overlap = calculate_overlap(
        prev_turn.start_s,
        prev_turn.end_s,
        next_turn.start_s,
        next_turn.end_s,
    )

    is_interruption = overlap > 0.0
    interrupter = None
    if is_interruption:
        # If next turn starts while prev turn is still speaking, next turn is the interrupter
        if prev_turn.end_s is not None and next_turn.start_s is not None and next_turn.start_s < prev_turn.end_s:
            interrupter = next_turn.speaker

    latency = calculate_response_latency(prev_turn.end_s, next_turn.start_s)
    silence_gap = latency if (latency is not None and latency > 0.0) else None

    return TurnTimingAnalysis(
        prev_turn_index=prev_turn.turn_index,
        next_turn_index=next_turn.turn_index,
        overlap_s=overlap,
        is_interruption=is_interruption,
        interrupter=interrupter,
        response_latency_s=latency,
        silence_gap_s=silence_gap,
    )

