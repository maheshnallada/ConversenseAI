import pytest
from app.domain.transcript import TranscriptTurn
from app.reconstruction.reconciliation import DeliveryClassification, classify_delivery


def _turn(speaker="agent", spoken=None, heard_text=None, raw_text="Sample"):
    return TranscriptTurn(
        turn_id="t1",
        interaction_id="i1",
        tenant_id="ten1",
        turn_index=0,
        speaker=speaker,
        raw_text=raw_text,
        normalized_text=raw_text.lower(),
        playback_spoken=spoken,
        playback_heard_text=heard_text,
    )


def test_classify_heard():
    turn = _turn(spoken="heard")
    res: DeliveryClassification = classify_delivery(turn)
    assert res.status == "heard"
    assert res.is_agent is True
    assert res.was_heard is True
    assert res.was_cut is False


def test_classify_cut():
    turn = _turn(spoken="cut", heard_text="Partial words")
    res = classify_delivery(turn)
    assert res.status == "cut"
    assert res.was_cut is True
    assert res.was_heard is True  # partially heard
    assert res.heard_text == "Partial words"


def test_classify_not_played():
    turn = _turn(spoken="not_played")
    res = classify_delivery(turn)
    assert res.status == "not_played"
    assert res.was_heard is False
    assert res.was_cut is False


def test_classify_no_audio():
    turn = _turn(spoken="no_audio")
    res = classify_delivery(turn)
    assert res.status == "no_audio"
    assert res.was_heard is False


def test_classify_unknown_when_spoken_is_none():
    turn = _turn(spoken=None)
    res = classify_delivery(turn)
    assert res.status == "unknown"
    assert res.was_heard is None  # Unknown evidence!


def test_classify_mismatch():
    # If marked not_played but heard text is present, evidence is conflicting
    turn = _turn(spoken="not_played", heard_text="Someone heard this!")
    res = classify_delivery(turn)
    assert res.status == "mismatch"


def test_classify_customer_turn():
    turn = _turn(speaker="customer")
    res = classify_delivery(turn)
    assert res.status == "customer_turn"
    assert res.is_agent is False

