import pytest
from app.domain.transcript import TranscriptTurn
from app.observability.calculator import (
    calculate_percentiles,
    extract_sequential_latencies,
    calculate_interaction_metrics,
)
from app.observability.config import RateCardManager


def test_calculate_percentiles_empty():
    res = calculate_percentiles([])
    assert res.avg is None
    assert res.p50 is None
    assert res.p90 is None
    assert res.p95 is None
    assert res.p99 is None


def test_calculate_percentiles_single_value():
    res = calculate_percentiles([1.25])
    assert res.avg == 1.25
    assert res.p50 == 1.25
    assert res.p90 == 1.25


def test_calculate_percentiles_sample_distribution():
    # 5 values: 1.0, 2.0, 3.0, 4.0, 5.0 -> median=3.0, avg=3.0
    res = calculate_percentiles([1.0, 2.0, 3.0, 4.0, 5.0])
    assert res.avg == 3.0
    assert res.p50 == 3.0
    assert res.p90 >= 4.0
    assert res.p99 <= 5.0


def test_extract_sequential_latencies():
    t1 = TranscriptTurn("t1", "i1", "t1", 0, "customer", "Hi", "hi", start_s=0.5, end_s=1.5)
    t2 = TranscriptTurn("t2", "i1", "t1", 1, "agent", "Hello", "hello", start_s=2.0, end_s=3.5)
    t3 = TranscriptTurn("t3", "i1", "t1", 2, "customer", "Yes", "yes", start_s=4.0, end_s=4.5)
    t4 = TranscriptTurn("t4", "i1", "t1", 3, "agent", "Sure", "sure", start_s=4.2, end_s=5.0)  # Overlap!

    # Only t1 -> t2 is sequential (latency = 0.5s); t3 -> t4 overlaps so it must NOT be included in sequential latency!
    latencies = extract_sequential_latencies([t1, t2, t3, t4])
    assert len(latencies) == 1
    assert latencies[0] == 0.5


def test_dual_duration_clocks_preserved():
    call_data = {
        "call_id": "call_17_test",
        "meta": {"usage": {"line": {"connected_s": 62.0}, "llm": {"total_input_tokens": 100, "total_output_tokens": 50}}},
        "models": {"provider": "gemini", "model": "gemini-3.5-flash-lite"},
    }
    turns = [
        TranscriptTurn("t1", "call_17_test", "ten1", 0, "agent", "Hi", "hi", start_s=1.0, end_s=2.5)
    ]
    # Recording WAV duration is 68.54s vs connected_s 62.0s
    metrics = calculate_interaction_metrics(
        tenant_id="ten1",
        interaction_id="call_17_test",
        call_data=call_data,
        turns=turns,
        recording_duration_s=68.54,
        rate_card=RateCardManager(),
    )
    assert metrics.telephony_duration_s == 62.0
    assert metrics.recording_duration_s == 68.54
    assert metrics.recording_duration_s != metrics.telephony_duration_s

