import pytest
from app.domain.transcript import TranscriptTurn
from app.reconstruction.failures import (
    FailureCategory,
    FailureRecord,
    detect_failures,
)


def _turn(index, speaker, start, end, spoken=None, text="Hello"):
    return TranscriptTurn(
        turn_id=f"t_{index}",
        interaction_id="i1",
        tenant_id="ten1",
        turn_index=index,
        speaker=speaker,
        raw_text=text,
        normalized_text=text.lower(),
        start_s=start,
        end_s=end,
        duration_s=round(end - start, 3) if (start is not None and end is not None) else None,
        playback_spoken=spoken,
    )


def test_detect_no_agent_audio():
    # Empty turns or customer-only turns
    turns = [_turn(0, "customer", 0.5, 2.0)]
    call_meta = {"agent_wav_count": 0}
    res = detect_failures(turns, call_meta)

    assert res.first_technical_failure is not None
    assert res.first_technical_failure.failure_type == "NO_AGENT_AUDIO"
    assert res.first_technical_failure.category == FailureCategory.TECHNICAL


def test_detect_late_agent_opening():
    # First agent words start at 4.2s (> 3.0s threshold)
    turns = [
        _turn(0, "agent", 4.2, 6.0, spoken="heard"),
        _turn(1, "customer", 6.5, 7.5),
    ]
    res = detect_failures(turns, {"agent_wav_count": 1})
    assert res.first_technical_failure is not None
    assert res.first_technical_failure.failure_type == "LATE_AGENT_OPENING"
    assert res.first_technical_failure.time_s == 4.2


def test_detect_agent_cut_and_customer_interruption():
    # Agent turn is cut at turn 0, customer interrupted at turn 1
    t0 = _turn(0, "agent", 0.5, 3.0, spoken="cut")
    t0.playback_heard_text = "Namaste, main..."
    t1 = _turn(1, "customer", 2.0, 4.0)  # Starts while agent is speaking

    turns = [t0, t1]
    res = detect_failures(turns, {"agent_wav_count": 1})

    assert res.first_technical_failure is not None
    assert res.first_technical_failure.failure_type == "AGENT_PLAYBACK_CUT"
    assert res.first_technical_failure.turn_index == 0

    assert res.first_conversational_failure is not None
    assert res.first_conversational_failure.failure_type == "CUSTOMER_INTERRUPTION"
    assert res.first_conversational_failure.turn_index == 1


def test_detect_agent_repetition():
    turns = [
        _turn(0, "agent", 0.5, 2.0, spoken="heard", text="Aapka naam kya hai?"),
        _turn(1, "customer", 2.5, 3.5, text="Haan?"),
        _turn(2, "agent", 4.0, 5.5, spoken="heard", text="Aapka naam kya hai?"),
    ]
    res = detect_failures(turns, {"agent_wav_count": 2})

    assert res.first_conversational_failure is not None
    assert res.first_conversational_failure.failure_type == "AGENT_REPETITION"
    assert res.first_conversational_failure.turn_index == 2

