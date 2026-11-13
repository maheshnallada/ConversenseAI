import pytest
from app.domain.transcript import TranscriptTurn
from app.reconstruction.timing import (
    calculate_overlap,
    calculate_response_latency,
    analyze_turn_pair,
)


def _turn(index, speaker, start, end):
    return TranscriptTurn(
        turn_id=f"t_{index}",
        interaction_id="i1",
        tenant_id="ten1",
        turn_index=index,
        speaker=speaker,
        raw_text="Text",
        normalized_text="text",
        start_s=start,
        end_s=end,
        duration_s=round(end - start, 3) if (start is not None and end is not None) else None,
    )


def test_calculate_overlap_no_overlap():
    # Turn 1: 0.0 - 2.0, Turn 2: 2.5 - 4.0
    assert calculate_overlap(0.0, 2.0, 2.5, 4.0) == 0.0


def test_calculate_overlap_positive():
    # Turn 1: 0.0 - 3.0, Turn 2: 2.0 - 4.0 (overlap between 2.0 and 3.0 = 1.0s)
    assert calculate_overlap(0.0, 3.0, 2.0, 4.0) == 1.0


def test_calculate_overlap_contained():
    # Turn 1: 1.0 - 5.0, Turn 2: 2.0 - 3.0 (overlap = 1.0s)
    assert calculate_overlap(1.0, 5.0, 2.0, 3.0) == 1.0


def test_sequential_latency():
    # Customer ended at 2.0, Agent started at 2.8 -> Latency = 0.8s
    latency = calculate_response_latency(2.0, 2.8)
    assert latency == 0.8


def test_overlapping_turns_prevent_negative_latency():
    # Customer turn from 0.0 to 3.0, Agent starts speaking at 2.0 (interruption)
    t1 = _turn(0, "customer", 0.0, 3.0)
    t2 = _turn(1, "agent", 2.0, 4.5)

    analysis = analyze_turn_pair(t1, t2)
    assert analysis.overlap_s == 1.0
    assert analysis.is_interruption is True
    # Latency should be None rather than -1.0s
    assert analysis.response_latency_s is None
    assert analysis.interrupter == "agent"


def test_missing_timestamps_handled_gracefully():
    t1 = _turn(0, "customer", None, None)
    t2 = _turn(1, "agent", 1.0, 2.0)

    analysis = analyze_turn_pair(t1, t2)
    assert analysis.overlap_s == 0.0
    assert analysis.is_interruption is False
    assert analysis.response_latency_s is None

