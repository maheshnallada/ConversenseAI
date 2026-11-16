import pytest

from app.domain.transcript import TranscriptTurn
from app.evaluation.evidence import validate_batch_evidence
from app.evaluation.schemas import (
    ComplianceAppointmentResult,
    CustomerFact,
    ConversationUnderstandingResult,
)


def _turn(index, speaker, text):
    return TranscriptTurn(
        turn_id=f"turn-{index}",
        interaction_id="interaction-1",
        tenant_id="tenant-1",
        turn_index=index,
        speaker=speaker,
        raw_text=text,
        normalized_text=text,
    )


def _understanding(
    *,
    outcome_line=None,
    outcome_quote="",
    sentiment_line=None,
    sentiment_quote="",
    emotion_line=None,
    emotion_quote="",
    customer_facts=None,
):
    return ConversationUnderstandingResult(
        outcome={
            "label": "Can't tell",
            "evidence_line": outcome_line,
            "quote": outcome_quote,
            "reason": "Not established.",
        },
        customer_facts=customer_facts or [],
        sentiment={
            "label": "Can't tell",
            "evidence_line": sentiment_line,
            "quote": sentiment_quote,
            "reason": "Not established.",
        },
        emotion={
            "label": "Can't tell",
            "evidence_line": emotion_line,
            "quote": emotion_quote,
            "reason": "Not established.",
        },
    )


def _compliance_appointment(
    *,
    consent_status="NOT_PRESENT",
    consent_evidence_line=None,
    consent_quote="",
):
    return ComplianceAppointmentResult(
        compliance={
            "rule_results": {
                f"NR00{index}": {
                    "status": "NOT_DETECTED",
                    "evidence_line": None,
                    "quote": "",
                    "reason": "",
                }
                for index in range(1, 7)
            },
            "potential_violations": [],
        },
        appointment_interpretation={
            "appointment_type": "EXPERT_CALL",
            "consent_status": consent_status,
            "consent_evidence_line": consent_evidence_line,
            "consent_quote": consent_quote,
            "agent_proposal_line": None,
            "agent_proposal_quote": "",
            "date_text": None,
            "time_text": None,
            "interpreted_date": None,
            "interpreted_time": None,
            "interpretation_reason": "Test interpretation.",
        },
    )


def test_exact_original_script_quote_is_valid():
    turns = [_turn(3, "customer", "నాకు policy కావాలి.")]
    result = _understanding(
        sentiment_line=3,
        sentiment_quote="నాకు policy కావాలి",
    )

    report = validate_batch_evidence("conversation_understanding", result, turns)

    assert report.schema_valid is True
    assert report.evidence_valid is True
    assert report.issues == []


def test_case_or_normalized_quote_change_is_rejected():
    turns = [_turn(1, "customer", "I already have insurance.")]
    result = _understanding(
        sentiment_line=1,
        sentiment_quote="i already have insurance",
    )

    report = validate_batch_evidence("conversation_understanding", result, turns)

    assert report.evidence_valid is False
    assert report.review_reasons


def test_unknown_evidence_line_is_rejected():
    turns = [_turn(1, "customer", "Please call me tomorrow.")]
    result = _understanding(outcome_line=99, outcome_quote="Please call me tomorrow.")

    report = validate_batch_evidence("conversation_understanding", result, turns)

    assert report.evidence_valid is False
    assert any("99" in issue for issue in report.issues)


def test_customer_fact_and_sentiment_cannot_cite_agent_turns():
    turns = [_turn(1, "agent", "You said you have insurance.")]
    result = _understanding(
        sentiment_line=1,
        sentiment_quote="You said you have insurance.",
        customer_facts=[
            CustomerFact(
                category="existing_insurance",
                field="has_existing_insurance",
                value=True,
                evidence_line=1,
                quote="You said you have insurance.",
            )
        ],
    )

    report = validate_batch_evidence("conversation_understanding", result, turns)

    assert report.evidence_valid is False
    assert any("customer" in issue.lower() for issue in report.issues)


def test_absent_optional_evidence_is_valid_and_not_fabricated():
    result = _understanding()

    report = validate_batch_evidence(
        "conversation_understanding",
        result,
        [_turn(1, "customer", "No result was established.")],
    )

    assert report.schema_valid is True
    assert report.evidence_valid is True
    assert report.issues == []


def test_empty_transcript_cannot_validate_batch_evidence():
    report = validate_batch_evidence(
        "conversation_understanding",
        _understanding(),
        [],
    )

    assert report.evidence_valid is False
    assert any("transcript is empty" in issue.lower() for issue in report.issues)


def test_explicit_consent_requires_customer_evidence():
    report = validate_batch_evidence(
        "compliance_appointment",
        _compliance_appointment(consent_status="EXPLICIT"),
        [_turn(1, "customer", "That sounds good.")],
    )

    assert report.evidence_valid is False
    assert any("consent" in issue.lower() for issue in report.issues)


def test_unqualified_acknowledgement_cannot_establish_explicit_consent():
    report = validate_batch_evidence(
        "compliance_appointment",
        _compliance_appointment(
            consent_status="EXPLICIT",
            consent_evidence_line=1,
            consent_quote="Okay.",
        ),
        [_turn(1, "customer", "Okay.")],
    )

    assert report.evidence_valid is False
    assert any("acknowledgement" in issue.lower() for issue in report.issues)


@pytest.mark.parametrize(
    ("field", "value", "quote"),
    [
        ("identity_card", "ABCDE1234F", "My PAN is ABCDE1234F."),
        ("identity_number", "1234 5678 9012", "My number is 1234 5678 9012."),
        ("verification_code", "123456", "I shared my OTP 123456."),
        ("bank_credentials", "secret-password", "My bank password is secret-password."),
    ],
)
def test_sensitive_customer_identifiers_are_flagged(field, value, quote):
    result = _understanding(
        customer_facts=[
            CustomerFact(
                category="other_relevant_facts",
                field=field,
                value=value,
                evidence_line=1,
                quote=quote,
            )
        ]
    )

    report = validate_batch_evidence(
        "conversation_understanding",
        result,
        [_turn(1, "customer", quote)],
    )

    assert report.evidence_valid is False
    assert report.sensitive_data_detected is True


def test_callback_phone_number_is_not_mistaken_for_sensitive_identifier():
    quote = "Please call me on +91 9876543210."
    result = _understanding(
        customer_facts=[
            CustomerFact(
                category="callback_details",
                field="phone_number",
                value="+91 9876543210",
                evidence_line=1,
                quote=quote,
            )
        ]
    )

    report = validate_batch_evidence(
        "conversation_understanding",
        result,
        [_turn(1, "customer", quote)],
    )

    assert report.evidence_valid is True
    assert report.sensitive_data_detected is False


def test_wrong_batch_model_is_reported_as_schema_invalid():
    report = validate_batch_evidence(
        "conversation_understanding",
        {},
        [],
    )

    assert report.schema_valid is False
    assert report.evidence_valid is False
    assert report.review_reasons
