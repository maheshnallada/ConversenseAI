import pytest
from app.domain.transcript import TranscriptTurn
from app.reconstruction.failures import (
    FailureCategory,
    FailureRecord,
    detect_failures,
    select_first_failure,
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


def test_late_agent_opening_remains_a_metric_not_a_failure():
    turns = [
        _turn(0, "agent", 4.2, 6.0, spoken="heard"),
        _turn(1, "customer", 6.5, 7.5),
    ]
    res = detect_failures(turns, {"agent_wav_count": 1})
    assert res.first_technical_failure is None
    assert all(failure.failure_type != "LATE_AGENT_OPENING" for failure in res.all_failures)


def test_missing_agent_turns_without_audio_evidence_are_not_failures():
    turns = [_turn(0, "customer", 0.5, 2.0)]

    res = detect_failures(turns, {})

    assert res.first_technical_failure is None
    assert all(failure.failure_type != "NO_AGENT_AUDIO" for failure in res.all_failures)


def test_original_turn_order_orders_failures_when_timestamps_are_unavailable():
    turns = [
        _turn(0, "agent", None, None, spoken="cut"),
        _turn(1, "agent", 5.0, 6.0, spoken="not_played"),
    ]

    res = detect_failures(turns, {"agent_wav_count": 2})

    assert [failure.failure_type for failure in res.all_failures] == [
        "AGENT_PLAYBACK_CUT",
        "AGENT_LINE_NOT_PLAYED",
    ]
    assert res.first_technical_failure is res.all_failures[0]
    assert res.technical_ordering_unknown is False


def test_failure_order_is_unknown_without_time_or_transcript_sequence():
    candidates = [
        FailureRecord("failure-a", FailureCategory.TECHNICAL, None, None, "evidence"),
        FailureRecord("failure-b", FailureCategory.TECHNICAL, None, None, "evidence"),
    ]

    first, ordering_unknown = select_first_failure(candidates)

    assert first is None
    assert ordering_unknown is True


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


def test_unplayed_turn_cancelled_by_customer_hangup_is_not_a_failure():
    # Customer hung up before/as the agent turn was queued
    t0 = _turn(0, "agent", 0.5, 2.5, spoken="heard", text="Hello?")
    t1 = _turn(1, "customer", 3.0, 3.5, text="Haan")
    t2 = _turn(2, "agent", 4.0, 5.5, spoken="not_played", text="Main Priya PolicyGuru se...")

    turns = [t0, t1, t2]
    call_meta = {
        "agent_wav_count": 1,
        "ended_at_seconds": 4.5,
        "end_reason": "dropped",
    }
    res = detect_failures(turns, call_meta)

    # Must NOT flag AGENT_LINE_NOT_PLAYED because customer hung up
    assert res.first_technical_failure is None
    assert all(f.failure_type != "AGENT_LINE_NOT_PLAYED" for f in res.all_failures)


def test_unplayed_turn_cancelled_by_customer_interruption_is_not_a_failure():
    # Customer spoke concurrently or right before the agent response was ready
    t0 = _turn(0, "agent", 0.5, 2.5, spoken="heard", text="Hello?")
    t1 = _turn(1, "customer", 5.0, 5.8, text="Abhi chal raha hai")
    t2 = _turn(2, "agent", 5.2, 7.0, spoken="not_played", text="Accha...")
    t3 = _turn(3, "agent", 6.5, 8.0, spoken="heard", text="Accha policy office se hai?")

    turns = [t0, t1, t2, t3]
    call_meta = {
        "agent_wav_count": 2,
        "ended_at_seconds": 20.0,
        "end_reason": "ended",
    }
    res = detect_failures(turns, call_meta)

    # Must NOT flag AGENT_LINE_NOT_PLAYED because customer interrupted/spoke concurrently
    assert res.first_technical_failure is None
    assert all(f.failure_type != "AGENT_LINE_NOT_PLAYED" for f in res.all_failures)


def test_unplayed_turn_during_active_call_is_technical_failure():
    # Call was active, customer was waiting, but agent audio never played
    t0 = _turn(0, "agent", 0.5, 2.5, spoken="heard", text="Hello?")
    t1 = _turn(1, "customer", 3.0, 3.5, text="Haan")
    t2 = _turn(2, "agent", 10.0, 12.0, spoken="not_played", text="Offer suniye...")
    t3 = _turn(3, "agent", 15.0, 17.0, spoken="heard", text="Aap sun rahe hain?")

    turns = [t0, t1, t2, t3]
    call_meta = {
        "agent_wav_count": 2,
        "ended_at_seconds": 30.0,
        "end_reason": "ended",
    }
    res = detect_failures(turns, call_meta)

    # Must flag AGENT_LINE_NOT_PLAYED because it was a genuine technical fault
    assert res.first_technical_failure is not None
    assert res.first_technical_failure.failure_type == "AGENT_LINE_NOT_PLAYED"
    assert res.first_technical_failure.turn_index == 2


