import pytest
from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.evaluation.compliance import ComplianceEvaluator


def _envelope(interaction_id="c1", domain_data=None):
    return InteractionEnvelope(
        tenant_id="ten1",
        interaction_id=interaction_id,
        schema_version="1.0",
        use_case="health_insurance",
        domain_data=domain_data or {},
    )


def test_never_rule_sensitive_data_detection():
    evaluator = ComplianceEvaluator()
    turn = TranscriptTurn(
        "t1", "c1", "ten1", 0, "agent",
        "Aap mujhe apna OTP ya Aadhaar number bata dijiye.",
        "aap mujhe apna otp ya aadhaar number bata dijiye.",
    )
    result = evaluator.evaluate(_envelope(), [turn])

    assert result.label == "FAILED"
    assert result.severity in ["high", "critical"]
    assert result.review_status == "FLAGGED_FOR_REVIEW"
    assert any("Aadhaar" in e.reason or "OTP" in e.reason for e in result.evidence)


def test_never_rule_premium_quote_detection():
    evaluator = ComplianceEvaluator()
    turn = TranscriptTurn(
        "t1", "c1", "ten1", 0, "agent",
        "Yeh policy aapko 5000 rupees per year mein milegi.",
        "yeh policy aapko 5000 rupees per year mein milegi.",
    )
    result = evaluator.evaluate(_envelope(), [turn])

    assert result.label == "FAILED"
    assert any("premium" in e.reason.lower() or "price" in e.reason.lower() for e in result.evidence)


def test_never_rule_ai_denial():
    evaluator = ComplianceEvaluator()
    t1 = TranscriptTurn("t1", "c1", "ten1", 0, "customer", "Are you an AI?", "are you an ai?")
    t2 = TranscriptTurn("t2", "c1", "ten1", 1, "agent", "No, I am a real human consultant sitting in office.", "no, i am a real human consultant sitting in office.")

    result = evaluator.evaluate(_envelope(), [t1, t2])
    assert result.label == "FAILED"
    assert any("AI" in e.reason for e in result.evidence)


def test_never_rule_appointment_outside_hours():
    evaluator = ComplianceEvaluator()
    # End call record booked at 07:00 (outside 09:00 - 21:00)
    domain_data = {
        "meta": {
            "end_call": {
                "outcome": "CALLBACK_BOOKED",
                "record": {"time": "07:00", "date": "2026-11-05"},
            }
        }
    }
    env = _envelope(domain_data=domain_data)
    result = evaluator.evaluate(env, [])
    assert result.label == "FAILED"
    assert any("9 AM" in e.reason or "07:00" in e.reason for e in result.evidence)


def test_compliant_call_passes():
    evaluator = ComplianceEvaluator()
    turn = TranscriptTurn(
        "t1", "c1", "ten1", 0, "agent",
        "Namaste, main PolicyGuru se bol raha hoon. Kya main aapke health plan ke baare mein baat kar sakta hoon?",
        "namaste, main policyguru se bol raha hoon. kya main aapke health plan ke baare mein baat kar sakta hoon?",
    )
    result = evaluator.evaluate(_envelope(), [turn])
    assert result.label == "PASSED"
    assert result.review_status == "PASSED"
    assert len(result.evidence) == 0

