import pytest
from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.evaluation.outcome import OutcomeEvaluator
from app.evaluation.llm_client import LLMClient

def _envelope(interaction_id="call_test_1"):
    return InteractionEnvelope(
        tenant_id="test_tenant",
        interaction_id=interaction_id,
        schema_version="1.0",
        use_case="health_insurance",
    )

def test_outcome_evaluator_not_interested():
    client = LLMClient()
    evaluator = OutcomeEvaluator(llm_client=client)

    turns = [
        TranscriptTurn("t1", "c1", "ten1", 1, "agent", "Hello, I am calling from PolicyGuru regarding health insurance.", "hello"),
        TranscriptTurn("t2", "c1", "ten1", 2, "customer", "I am not interested, thank you.", "i am not interested, thank you."),
        TranscriptTurn("t3", "c1", "ten1", 3, "agent", "Thank you, have a good day.", "thank you")
    ]

    res = evaluator.evaluate(_envelope("c1"), turns)
    assert res.label == "Not interested"
    assert res.details["correct_outcome"] == "Not interested"
    assert len(res.evidence) > 0
    assert any(e.line_index == 2 for e in res.evidence)

def test_outcome_evaluator_do_not_call():
    evaluator = OutcomeEvaluator()
    turns = [
        TranscriptTurn("t1", "c_dnc", "ten1", 1, "agent", "Hello, I am calling from PolicyGuru.", "hello"),
        TranscriptTurn("t2", "c_dnc", "ten1", 2, "customer", "Please remove my number and do not call again.", "please remove my number and do not call again.")
    ]
    res = evaluator.evaluate(_envelope("c_dnc"), turns)
    assert res.label == "Do not call"

def test_outcome_evaluator_call_later():
    evaluator = OutcomeEvaluator()
    turns = [
        TranscriptTurn("t1", "c2", "ten1", 1, "agent", "Hello, calling regarding health insurance.", "hello"),
        TranscriptTurn("t2", "c2", "ten1", 2, "customer", "I am driving right now, please call me back later in the evening.", "i am driving right now, please call me back later in the evening.")
    ]
    res = evaluator.evaluate(_envelope("c2"), turns)
    assert res.label == "Call later agreed"

def test_outcome_evaluator_expert_call_booked():
    evaluator = OutcomeEvaluator()
    turns = [
        TranscriptTurn("t1", "c3", "ten1", 1, "agent", "Can we schedule our expert to call you tomorrow at 4 PM?", "can we schedule our expert to call you tomorrow at 4 pm?"),
        TranscriptTurn("t2", "c3", "ten1", 2, "customer", "Yes, that works, please book it.", "yes, that works, please book it.")
    ]
    res = evaluator.evaluate(_envelope("c3"), turns)
    assert res.label == "Expert call booked"

def test_outcome_evaluator_voicemail():
    evaluator = OutcomeEvaluator()
    turns = [
        TranscriptTurn("t1", "c4", "ten1", 1, "agent", "Hello?", "hello?"),
        TranscriptTurn("t2", "c4", "ten1", 2, "customer", "Please leave a message after the beep. [beep]", "please leave a message after the beep. [beep]")
    ]
    res = evaluator.evaluate(_envelope("c4"), turns)
    assert res.label == "Voicemail"
